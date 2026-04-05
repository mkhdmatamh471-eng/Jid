import os # تأكد من استيراد os

async def get_qr_from_bridge(store_id):
    """تشغيل Node.js مع تمرير مفاتيح Supabase للعملية الفرعية"""
    logger.info(f"🚀 [STEP 1] Starting Bridge for Store: {store_id}...")
    
    # استخراج مفاتيح Supabase من بيئة النظام (التي عرفتها في Render)
    # لتمريرها لعملية Node.js
    env_vars = os.environ.copy()
    
    process = None
    try:
        # تشغيل ملف الجافاسكريبت مع تمرير env_vars
        process = await asyncio.create_subprocess_exec(
            'node', 'wa-bridge.js', store_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env_vars # مررنا المتغيرات هنا ليعرف Node كيف يتصل بسوبابيز
        )
        
        logger.info(f"📡 [STEP 2] Node.js process started (PID: {process.pid})")

        start_time = time.time()
        # رفع المهلة لـ 60 ثانية لضمان وقت كافٍ للمزامنة مع Supabase في بيئة Render
        while time.time() - start_time < 60:
            line = await process.stdout.readline()
            if not line:
                if process.returncode is not None:
                    logger.error(f"⚠️ [WARNING] Node process exited with code: {process.returncode}")
                break
            
            line_decode = line.decode().strip()
            
            if line_decode:
                logger.info(f"🖥️ [NODE_LOG]: {line_decode}")
            
            # 1. التقاط نص الباركود الخام
            if "QR_DATA_START:" in line_decode:
                raw_qr = line_decode.split("QR_DATA_START:")[1].split(":QR_DATA_END")[0]
                logger.info(f"✅ [STEP 3] Raw QR String Received: {raw_qr[:15]}...")
                
                base64_image = text_to_base64_qr(raw_qr)
                
                # لا نغلق العملية فوراً، ننتظر قليلاً للتأكد من اكتمال أي عملية رفع جارية
                process.terminate()
                await process.wait() 
                return base64_image

            # 2. التحقق مما إذا تم استرجاع الجلسة من Supabase بنجاح
            # أضفنا هذا الشرط لأن Node سيطبع SESSION_OPENED إذا استعاد الجلسة من القاعدة
            if "SESSION_OPENED" in line_decode:
                logger.info(f"🔗 [INFO] Session restored from Supabase for {store_id}")
                process.terminate()
                await process.wait()
                return "CONNECTED"

            # 3. تسجيل أخطاء المزامنة القادمة من Node
            if "[SYNC_ERROR]" in line_decode or "[RESTORE_ERROR]" in line_decode:
                logger.error(f"❌ [DB_ERROR]: {line_decode}")

        # مهلة الانتهاء
        elapsed = time.time() - start_time
        logger.error(f"⏳ [TIMEOUT] Bridge timed out after {elapsed:.2f}s")
        
        stderr_data = await process.stderr.read()
        if stderr_data:
            logger.error(f"❗ [STDERR]: {stderr_data.decode()}")

    except Exception as e:
        logger.error(f"❌ [CRITICAL] Exception in get_qr_from_bridge: {str(e)}")
    finally:
        if process and process.returncode is None:
            try:
                process.kill()
            except:
                pass
    return None
