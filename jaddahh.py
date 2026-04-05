import os
import hmac
import hashlib
import shutil
import tarfile
import json
import qrcode
import shutil
import qrcode
import base64
from io import BytesIO
import base64
from io import BytesIO
import json
import logging
import asyncio
import random
import tempfile
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import base64
import httpx
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from supabase import create_client, Client
from dotenv import load_dotenv
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta
import logging
import subprocess
import sqlite3
import json
import urllib.parse
from fastapi import APIRouter
import threading
from fastapi.responses import HTMLResponse
import psycopg2  
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse 
templates = Jinja2Templates(directory=".") 
# إعداد الـ Logger لضمان ظهور الأخطاء في سجلات ريندر

# --- 1. الإعدادات والتحميل ---
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jaddahh")

app = FastAPI(title="Salla AI Integrated Bot")
templates = Jinja2Templates(directory=".")

# إعدادات قاعدة البيانات والقنوات
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


SESSION_PATH = os.path.join(os.getcwd(), "whatsapp_session")

# تكوين البيئة
SESSION_PATH = os.path.join(os.getcwd(), "whatsapp_sessions")

latest_qrs = {}


# 2. جلب بقية المفاتيح
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# 3. إعدادات Salla (يفضل إضافتها أيضاً)
SALLA_CLIENT_ID = os.getenv("SALLA_CLIENT_ID")
SALLA_CLIENT_SECRET = os.getenv("SALLA_CLIENT_SECRET")
SALLA_WEBHOOK_SECRET = os.getenv("SALLA_WEBHOOK_SECRET")

# ========================================================
# --- 2. دوال توليد الباركود ونظام الجسر (الجديدة) ---
# ========================================================

def text_to_base64_qr(qr_text: str):
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_text)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        
        # استخدام .strip() للتأكد من عدم وجود مسافات زائدة
        img_str = base64.b64encode(buffered.getvalue()).decode().strip()
        return f"data:image/png;base64,{img_str}"
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return None

async def get_qr_from_bridge(store_id):
    """تشغيل Node.js وتمرير رابط قاعدة البيانات للربط المباشر"""
    logger.info(f"🚀 [STEP 1] Starting Bridge for Store: {store_id}...")
    
    # 1. نسخ متغيرات البيئة (بما فيها DATABASE_URL المعرف في Render)
    env_vars = os.environ.copy()
    
    # تأكد أن الرابط يبدأ بـ postgresql:// (تصحيح تلقائي إذا كان من Render)
    db_url = env_vars.get("DATABASE_URL", "")
    if db_url.startswith("postgres://"):
        env_vars["DATABASE_URL"] = db_url.replace("postgres://", "postgresql://", 1)

    process = None
    try:
        # 2. تشغيل Node.js مع تمرير env_vars
        process = await asyncio.create_subprocess_exec(
            'node', 'wa-bridge.js', store_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env_vars 
        )
        
        logger.info(f"📡 [STEP 2] Node.js started (PID: {process.pid})")

        start_time = time.time()
        # مهلة 60 ثانية لضمان وقت كافٍ للاتصال بالقاعدة والواتساب
        while time.time() - start_time < 60:
            line = await process.stdout.readline()
            if not line:
                break
            
            line_decode = line.decode().strip()
            if line_decode:
                logger.info(f"🖥️ [NODE_LOG]: {line_decode}")
            
            # حالة 1: استلام QR جديد (لم يسبق له الربط)
            if "QR_DATA_START:" in line_decode:
                raw_qr = line_decode.split("QR_DATA_START:")[1].split(":QR_DATA_END")[0]
                base64_image = text_to_base64_qr(raw_qr)
                # لا نغلق العملية فوراً، نتركها قليلاً لتكمل المزامنة إذا لزم الأمر
                return base64_image

            # حالة 2: تم استعادة الجلسة بنجاح من PostgreSQL
            if "SESSION_RESTORED_FROM_DB" in line_decode or "SESSION_OPENED" in line_decode:
                logger.info(f"✅ [SUCCESS] Store {store_id} is connected via PostgreSQL session.")
                return "CONNECTED"

            # حالة 3: فشل في الاتصال بالقاعدة من جهة Node
            if "DB_CONNECTION_ERROR" in line_decode:
                logger.error(f"❌ [DB_ERROR] Node.js failed to connect to Postgres")

    except Exception as e:
        logger.error(f"❌ [CRITICAL] Bridge Exception: {str(e)}")
    finally:
        if process and process.returncode is None:
            try:
                process.terminate()
            except:
                pass
    return None


# ========================================================
# --- 3. روابط الـ API (Endpoints) ---
# ========================================================

@app.get("/api/whatsapp/get-qr/{store_id}")
async def fetch_qr(store_id: str):
    """الرابط الذي تستدعيه لوحة التحكم لعرض الباركود"""
    base64_qr = await get_qr_from_bridge(store_id)
    
    if base64_qr == "CONNECTED":
        return {"status": "success", "message": "المتجر متصل بالفعل ✅", "code": 200}
    
    if base64_qr:
        return {
            "status": "qr_ready",
            "qr_image": base64_qr,
            "message": "تم توليد الباركود بنجاح"
        }
    
    return {"status": "error", "message": "فشل في توليد الباركود، حاول مجدداً"}

# ... بقية الدوال الخاصة بك (get_db_connection, execute_db_query, salla_request, etc.) ...
# [ملاحظة: تأكد من إبقاء بقية الكود كما هو بالأسفل]

# --- قسم Baileys الجديد ---
class BaileysDirectHandler:
    def __init__(self, store_id: str):
        self.store_id = store_id
        self.process = None

    async def start_session(self):
        """تشغيل عملية Node.js للجلسة"""
        # 1. تشغيل العملية
        self.process = subprocess.Popen(
            ["node", "wa-bridge.js", self.store_id],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # هام جداً لضمان القراءة السطرية الفورية
        )
        
        # 2. إضافة الـ Thread هنا (المكان الصحيح)
        # يبدأ بمجرد إنشاء العملية ليراقب الـ stdout الخاص بها
        thread = threading.Thread(
            target=monitor_output, 
            args=(self.process, self.store_id), 
            daemon=True
        )
        thread.start()
        
        logger.info(f"🚀 Started Baileys Bridge & Monitor for Store: {self.store_id}")

    async def send_text(self, phone: str, text: str):
        """إرسال أمر للملف البرمجي Node.js"""
        clean_phone = "".join(filter(str.isdigit, phone))
        # التأكد من أننا نرسل التنسيق الذي يتوقعه ملف wa-bridge.js (SEND:رقم|نص)
        command = f"SEND:{clean_phone}|{text}\n"
        
        # التأكد من أن العملية تعمل قبل الإرسال
        if self.process is None or self.process.poll() is not None:
            await self.start_session()
            # ننتظر قليلاً لضمان بدء التشغيل قبل الكتابة في stdin
            import asyncio
            await asyncio.sleep(1)

        try:
            if self.process and self.process.stdin:
                self.process.stdin.write(command)
                self.process.stdin.flush()
                return True
        except Exception as e:
            logger.error(f"❌ Failed to write to Node.js stdin: {e}")
        return False

# استبدل الـ Handler القديم في كودك بهذا
async def get_handler_for_store(store_id: str):
    return BaileysDirectHandler(store_id)

def execute_db_query(query: str, params: dict = None, fetch: str = None):
    """
    نسخة احترافية تدعم التراجع التلقائي في حال الخطأ (Rollback)
    وتوافق مع SQLAlchemy 2.0
    """
    try:
        with engine.connect() as connection:
            # استخدام begin لضمان تنفيذ العملية ككتلة واحدة (Transaction)
            with connection.begin():
                result = connection.execute(text(query), params or {})
                
                if fetch == "one":
                    return result.fetchone()
                if fetch == "all":
                    return result.fetchall()
                
                # ملاحظة: connection.begin() تقوم بعمل commit تلقائياً عند الخروج من الـ with
                return result
    except Exception as e:
        logger.error(f"❌ Database Query Error: {e}")
        # رفع الخطأ ضروري لكي تظهر تفاصيله في سجلات Render
        raise e
        
async def message_worker():
    while True:
        # الآن الـ Queue يستقبل 3 قيم
        store_id, phone, text = await message_queue.get()
        try:
            await send_via_web_bridge(store_id, phone, text)
            await asyncio.sleep(random.uniform(2, 5)) 
        except Exception as e:
            logger.error(f"Worker error: {e}")
        finally:
            message_queue.task_done()
        

# طابور الرسائل يبقى كما هو
message_queue = asyncio.Queue()

async def whatsapp_worker():
    """عامل خلفية لمعالجة الرسائل من الطابور دون تعطيل الـ Webhook"""
    while True:
        # جلب المهمة التالية من الطابور
        task = await message_queue.get()
        store_id, phone, message = task
        
        try:
            # استدعاء دالة الإرسال التي جهزناها سابقاً
            success = await send_whatsapp_message(store_id, phone, message)
            if success:
                logger.info(f"✅ تم معالجة الرسالة لـ {phone} من الطابور")
        except Exception as e:
            logger.error(f"❌ خطأ في عامل الـ WhatsApp: {e}")
        finally:
            message_queue.task_done()

# لا تنسى تشغيل العامل عند بدء تشغيل FastAPI

# تشغيل العامل عند بدء التطبيق

def verify_salla_signature(payload: bytes, signature: str, secret: str):
    computed_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_sig, signature)

# --- خدمات SALLA (Authentication & Data) ---
# نحتاج لتخزين كائن playwright لإغلاقه بشكل صحيح




def monitor_output(process, store_id):
    """
    مراقب مخرجات عملية Node.js:
    يقوم بالتقاط الباركود، حالة الاتصال، والرسائل الواردة وتمريرها للمعالجة.
    """
    # قراءة المخرجات سطر بسطر من عملية الجسر (wa-bridge.js)
    for line in iter(process.stdout.readline, ''):
        line = line.strip()
        if not line:
            continue

        # 1. حالة استلام باركود جديد
        if "QR_DATA_START:" in line:
            try:
                qr_code = line.split("QR_DATA_START:")[1].split(":QR_DATA_END")[0]
                latest_qrs[store_id] = qr_code
                logger.info(f"✨ [QR] New code generated for Store: {store_id}")
            except Exception as e:
                logger.error(f"❌ Error parsing QR: {e}")

        # 2. حالة نجاح فتح الجلسة (سواء لأول مرة أو استعادة من القاعدة)
        elif "SESSION_OPENED" in line:
            latest_qrs[store_id] = "CONNECTED"
            logger.info(f"✅ [AUTH] Store {store_id} is now ONLINE (Postgres Session)")

        # 3. حالة استلام رسالة جديدة من عميل (التمرير للذكاء الاصطناعي)
        elif "NEW_MSG|" in line:
            try:
                # التنسيق المتوقع من wa-bridge.js هو: NEW_MSG|sender_phone|message_text
                parts = line.split("|")
                if len(parts) >= 3:
                    sender_phone = parts[1]
                    message_text = "|".join(parts[2:]) # لضمان عدم ضياع النص لو احتوى على |
                    
                    logger.info(f"📩 [INCOMING] From {sender_phone} @ {store_id}: {message_text}")
                    
                    # تمرير الرسالة لمعالج الذكاء الاصطناعي في الخلفية
                    # نستخدم run_coroutine_threadsafe لأن هذه الدالة تعمل في Thread مستقل
                    asyncio.run_coroutine_threadsafe(
                        process_customer_request(store_id, sender_phone, message_text),
                        asyncio.get_event_loop()
                    )
            except Exception as e:
                logger.error(f"❌ Error routing incoming message: {e}")

        # 4. تأكيد إرسال رسالة (Outbound Confirmation)
        elif "SENT_CONFIRMATION:" in line:
            recipient = line.split("SENT_CONFIRMATION:")[1]
            logger.info(f"📤 [SENT] Message delivered to {recipient} via Store {store_id}")

        # 5. تسجيل أخطاء Node.js العامة
        elif "CRITICAL_NODE_ERROR" in line:
            logger.error(f"🚨 [NODE CRITICAL] {line}")

# تحديد مسار حفظ بيانات الجلسة (سيتم إنشاء مجلد في نفس مسار السكربت)




# استدعِ الدالة قبل البدء بطلب باركود جديد




# 🚦 التحكم في تدفق الموارد لحماية الرام في Render
# نضبطه على 1 لضمان عدم انهيار السيرفر نهائياً (يسمح بفتح متصفح واحد فقط في نفس اللحظة للربط)





# ========================================================
# الجسر السحري (Alias) للحفاظ على توافقية بقية الكود
# ========================================================

async def ensure_browser_ready(store_id: str):
    """
    دالة توجيهية: تم دمج منطقها مع get_handler_for_store.
    هذه الدالة موجودة فقط لكي لا يحدث أي خطأ (ImportError أو NameError) 
    في بقية الملفات التي تعتمد على هذا الاسم.
    """
    return await get_handler_for_store(store_id)





async def on_new_message_logic(payload):
    """
    دالة للبحث عن المحادثات غير المقروءة، الضغط عليها، استخراج النص، والرد.
    """
    # استخراج معرف المتجر من الـ payload (تأكد من مطابقة المفتاح لبياناتك)
    store_id = payload.get("store_id", "default_store") 
    logger.info(f"🔍 بدء فحص الرسائل الجديدة للمتجر: {store_id}")
    
    try:
        # 1. جلب الصفحة المفتوحة الخاصة بهذا المتجر
        page = await get_handler_for_store(store_id)
        
        # 2. محددات (Selectors) البحث عن الرسائل غير المقروءة باللغتين العربية والإنجليزية
        unread_selector = 'span[aria-label*="غير مقروء"], span[aria-label*="unread"]'
        
        # الانتظار لمدة 5 ثوانٍ للتحقق من وجود أي رسالة جديدة
        try:
            await page.wait_for_selector(unread_selector, timeout=5000)
        except:
            logger.info("📭 لا توجد محادثات غير مقروءة حالياً.")
            return

        # جلب جميع المحادثات غير المقروءة
        unread_elements = await page.locator(unread_selector).all()
        
        # 3. المرور على المحادثات الجديدة واحدة تلو الأخرى
        for unread in unread_elements:
            try:
                # الضغط على المحادثة لفتحها
                await unread.click()
                await asyncio.sleep(1.5)  # انتظار بسيط لضمان تحميل المحادثة بالكامل
                
                # 4. استخراج اسم أو رقم العميل من رأس الصفحة (Header)
                header_title = page.locator('header span[title]').first
                customer_info = await header_title.get_attribute("title") if await header_title.count() > 0 else "غير معروف"
                
                # 5. استخراج آخر رسالة مستلمة (نبحث في الرسائل الواردة إلينا فقط 'message-in')
                last_msg_locator = page.locator('div.message-in span.selectable-text').last
                
                if await last_msg_locator.count() > 0:
                    message_text = await last_msg_locator.inner_text()
                    logger.info(f"✅ رسالة جديدة من [{customer_info}]: {message_text}")
                    
                    # ==========================================
                    # 6. تمرير النص للذكاء الاصطناعي وتجهيز الرد
                    # ==========================================
                    # هنا نربط مع دالة GROQ التي كتبناها سابقاً
                    # ai_reply = await process_customer_request(store_id, customer_info, message_text)
                    
                    # نص تجريبي مؤقت للتأكد من عمل الكود:
                    ai_reply = f"أهلاً بك، استلمت رسالتك: '{message_text}'. جاري معالجتها..."
                    
                    # 7. كتابة الرد في صندوق المحادثة وإرساله
                    chat_input = page.locator('div[contenteditable="true"][data-tab="10"], div[contenteditable="true"][title="كتب رسالة"]')
                    await chat_input.fill(ai_reply)
                    await page.keyboard.press("Enter")
                    
                    logger.info(f"📤 تم الرد على [{customer_info}] بنجاح.")
                    await asyncio.sleep(1) # فاصل زمني لتجنب حظر واتساب
                
            except Exception as inner_e:
                logger.error(f"⚠️ خطأ أثناء التعامل مع محادثة {customer_info}: {inner_e}")
                continue

    except Exception as e:
        logger.error(f"❌ خطأ عام في دالة on_new_message_logic: {e}")



# الاستخدام داخل الكود
# await page.route("**/*", block_useless_resources)

# داخل دالة فتح الصفحة


async def salla_request(method: str, endpoint: str, store_id: str, payload: dict = None):
    """
    دالة موحدة لطلبات سلة:
    1. تقرأ من أي حقل توكن متاح (salla_access_token أو access_token).
    2. تعالج الخطأ 404 عبر التأكد من المسار.
    3. تجدد التوكن تلقائياً عند الخطأ 401.
    """
    try:
        # 1. جلب التوكن بذكاء (يأخذ أول قيمة غير فارغة تقابله من الحقلين)
        query = """
            SELECT COALESCE(salla_access_token, access_token) 
            FROM store_settings 
            WHERE store_id = :sid 
            LIMIT 1
        """
        row = execute_db_query(query, {"sid": store_id}, fetch="one")
        
        if not row or not row[0]:
            logger.error(f"❌ فشل جلب التوكن للمتجر {store_id}: كلا حقلي التوكن فارغين.")
            return None
            
        token = row[0]
        # تأكد أن endpoint لا يبدأ بـ / لتجنب مشاكل الروابط
        clean_endpoint = endpoint.lstrip('/')
        url = f"https://api.salla.dev/admin/v2/{clean_endpoint}"
        
        headers = {
            "Authorization": f"Bearer {token}", 
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 2. تنفيذ الطلب
            if method.upper() == "GET":
                resp = await client.get(url, headers=headers)
            else:
                resp = await client.post(url, headers=headers, json=payload)
                
            # 3. معالجة انتهاء صلاحية التوكن (401)
            if resp.status_code == 401:
                logger.warning(f"🔄 توكن المتجر {store_id} منتهي، جاري التجديد وتحديث الحقلين...")
                new_token = await refresh_salla_token(store_id)
                
                if new_token:
                    # إعادة المحاولة بالتوكن الجديد
                    headers["Authorization"] = f"Bearer {new_token}"
                    if method.upper() == "GET":
                        resp = await client.get(url, headers=headers)
                    else:
                        resp = await client.post(url, headers=headers, json=payload)
                else:
                    return None

            # 4. إعادة البيانات إذا كان الطلب ناجحاً
            if resp.status_code in [200, 201]:
                return resp.json()
            else:
                logger.error(f"⚠️ Salla API Error [{resp.status_code}] على {endpoint}: {resp.text}")
                return None

    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في salla_request: {str(e)}")
        return None

async def refresh_salla_token(store_id: str) -> Optional[str]:
    """تجديد التوكن وتحديث كلا الحقلين في قاعدة البيانات لضمان التطابق"""
    try:
        # جلب الـ refresh_token فقط من القاعدة
        query = "SELECT refresh_token FROM store_settings WHERE store_id = :sid"
        row = execute_db_query(query, {"sid": store_id}, fetch="one")
        
        if not row or not row[0]:
            logger.error(f"❌ لا يوجد refresh_token للمتجر {store_id}")
            return None
        
        url = "https://accounts.salla.sa/oauth2/token"
        payload = {
            "client_id": os.getenv("SALLA_CLIENT_ID"),
            "client_secret": os.getenv("SALLA_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": row[0]
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=payload)
            if resp.status_code == 200:
                data = resp.json()
                new_access = data["access_token"]
                new_refresh = data["refresh_token"]

                # تحديث الحقلين (salla_access_token و access_token) معاً ليكونوا "نفس بعض"
                update_query = """
                    UPDATE store_settings 
                    SET salla_access_token = :access, 
                        access_token = :access, 
                        refresh_token = :refresh, 
                        updated_at = NOW() 
                    WHERE store_id = :sid
                """
                execute_db_query(update_query, {
                    "access": new_access,
                    "refresh": new_refresh,
                    "sid": store_id
                })
                logger.info(f"✅ تم تجديد وتوحيد التوكنات للمتجر {store_id} بنجاح.")
                return new_access
            else:
                logger.error(f"❌ فشل تجديد التوكن من سلة: {resp.text}")
                return None
    except Exception as e:
        logger.error(f"❌ خطأ أثناء عملية التجديد: {e}")
        return None
async def refresh_salla_token(store_id: str) -> Optional[str]:
    """
    تجديد التوكن وتحديث الحقلين (salla_access_token و access_token) معاً لضمان التطابق.
    """
    try:
        # 1. جلب الـ refresh_token الحالي من القاعدة
        query = "SELECT refresh_token FROM store_settings WHERE store_id = :sid"
        row = execute_db_query(query, {"sid": store_id}, fetch="one")
        
        if not row or not row[0]:
            logger.error(f"❌ لا يوجد refresh_token للمتجر {store_id} في قاعدة البيانات.")
            return None
        
        # 2. إعداد طلب التجديد لـ Salla OAuth
        url = "https://accounts.salla.sa/oauth2/token"
        payload = {
            "client_id": os.getenv("SALLA_CLIENT_ID"),         # مفتاح تطبيقك من Render Env
            "client_secret": os.getenv("SALLA_CLIENT_SECRET"), # سر تطبيقك من Render Env
            "grant_type": "refresh_token",
            "refresh_token": row[0]
        }
        
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, data=payload)
            
            if resp.status_code == 200:
                data = resp.json()
                new_access = data["access_token"]
                new_refresh = data["refresh_token"]

                # 3. تحديث البيانات: جعل الحقلين "نفس بعض" تلقائياً
                update_query = """
                    UPDATE store_settings 
                    SET salla_access_token = :access, 
                        access_token = :access, 
                        refresh_token = :refresh, 
                        updated_at = NOW() 
                    WHERE store_id = :sid
                """
                execute_db_query(update_query, {
                    "access": new_access,
                    "refresh": new_refresh,
                    "sid": store_id
                })
                
                logger.info(f"✅ تم تجديد وتوحيد التوكنات للمتجر {store_id} بنجاح.")
                return new_access
            else:
                logger.error(f"❌ فشل تجديد التوكن من سلة: {resp.status_code} - {resp.text}")
                return None

    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع أثناء تجديد التوكن للمتجر {store_id}: {str(e)}")
        return None


async def get_salla_order(order_id: str, store_id: str) -> Optional[str]:
    """جلب بيانات الطلب من سلة باستخدام PostgreSQL لجلب التوكن"""
    try:
        # 1. جلب التوكن مباشرة من PostgreSQL
        query = "SELECT salla_access_token FROM store_settings WHERE store_id = :sid LIMIT 1"
        row = execute_db_query(query, {"sid": store_id}, fetch="one")
        
        if not row:
            logger.error(f"❌ لم يتم العثور على إعدادات للمتجر {store_id}")
            return None
            
        token = row[0]
        
        url = f"https://api.salla.dev/admin/v2/orders/{order_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            
            # 2. إذا انتهى التوكن (401)، نقوم بتجديده
            if resp.status_code == 401:
                logger.info(f"🔄 التوكن انتهى للمتجر {store_id}، جاري التجديد...")
                new_token = await refresh_salla_token(store_id)
                if new_token:
                    headers["Authorization"] = f"Bearer {new_token}"
                    resp = await client.get(url, headers=headers)
            
            # 3. معالجة بيانات الطلب
            if resp.status_code == 200:
                d = resp.json()["data"]
                # تنسيق الرد للعميل
                ref_id = d.get('reference_id')
                status_name = d.get('status', {}).get('name', 'غير معروفة')
                tracking = d.get('shipping', {}).get('tracking_link')
                
                msg = f"📦 تفاصيل الطلب رقم {ref_id}:\n- الحالة: {status_name}"
                if tracking:
                    msg += f"\n- رابط التتبع: {tracking}"
                else:
                    msg += "\n- التتبع: سيتم تحديثه قريباً."
                
                return msg

        return None

    except Exception as e:
        logger.error(f"❌ خطأ في get_salla_order للمتجر {store_id}: {e}")
        return "عذراً، لم أتمكن من جلب تفاصيل الطلب حالياً."

# --- خدمات الذكاء الاصطناعي (GROQ xAI) ---

async def groq_analyze_intent(message: str) -> dict:
    """
    تحليل نية العميل لاستخراج رقم الطلب أو اسم المنتج بدقة عالية باستخدام Llama 3.3
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.error("❌ GROQ_API_KEY is missing")
        return {"is_order": False, "order_id": None, "is_product": False, "product_name": None}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # تحسين البرومبت ليكون أكثر صرامة مع الـ JSON
    prompt = """
    أنت محلل نصوص خبير لمتجر إلكتروني سعودي. حلل رسالة العميل واستخرج البيانات التالية بصيغة JSON فقط:
    1. is_order: (bool) true إذا كان العميل يسأل عن (تتبع، حالة شحن، تعديل طلب، أو طلب سابق).
    2. order_id: (string) استخرج رقم الطلب (أرقام فقط). إذا لم يوجد ضع null.
    3. is_product: (bool) true إذا كان يسأل عن (توفر، سعر، أو تفاصيل منتج).
    4. product_name: (string) اسم المنتج المستخلص. إذا لم يوجد ضع null.

    قاعدة هامة: أجب بصيغة JSON فقط.
    """
    
    payload = {
        # التحديث هنا: استخدام الموديل الأحدث والأذكى للتحليل المعقد
        "model": "llama-3.3-70b-versatile", 
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message}
        ],
        "temperature": 0, # صفر لضمان استجابة منطقية وثابتة (Deterministic)
        "response_format": {"type": "json_object"} 
    }
    
    async with httpx.AsyncClient() as client:
        try:
            # تقليل التايم آوت قليلاً لسرعة استجابة البوت
            r = await client.post(url, json=payload, headers=headers, timeout=12.0)
            
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"]
                return json.loads(content)
            
            # في حال كان الموديل 70B مشغولاً (Rate Limit)، يمكن التبديل آلياً لـ 8B كخطة بديلة
            elif r.status_code == 429:
                logger.warning("⚠️ 70B model busy, switching to 8B for intent analysis")
                payload["model"] = "llama-3.1-8b-instant"
                r = await client.post(url, json=payload, headers=headers, timeout=10.0)
                if r.status_code == 200:
                    return json.loads(r.json()["choices"][0]["message"]["content"])

            logger.error(f"❌ Groq API Error: {r.status_code} - {r.text}")
            return {"is_order": False, "order_id": None, "is_product": False, "product_name": None}
                
        except Exception as e:
            logger.error(f"❌ Error in groq_analyze_intent: {str(e)}")
            return {"is_order": False, "order_id": None, "is_product": False, "product_name": None}

async def groq_generate_reply(history: List[Dict], context: str, system_prompt: str) -> str:
    """توليد رد بشري ذكي مع محاكاة التأخير البشري وتصحيح الموديل"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    # جلب مفتاح API من البيئة
    api_key = os.getenv("GROQ_API_KEY") 
    if not api_key:
        logger.error("❌ GROQ_API_KEY is missing from environment variables")
        return "عذراً، نظام الذكاء الاصطناعي غير مهيأ حالياً."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # تحسين السياق وضمان عدم إرسال None
    extra_context = context if context else "لا توجد بيانات طلب محددة. أجب بناءً على معلومات المتجر العامة."
    full_system = f"{system_prompt}\n\n[سياق النظام الحالي]:\n{extra_context}"
    
    # تقليص التاريخ لتقليل عدد الـ Tokens وسرعة الاستجابة
    compact_history = history[-6:]
    messages = [{"role": "system", "content": full_system}] + compact_history

    # 1. محاكاة وقت القراءة (تأخير واقعي)
    await asyncio.sleep(random.uniform(1.2, 2.5))

    async with httpx.AsyncClient() as client:
        try:
            # التحديث الأساسي هنا: تغيير الموديل إلى الإصدار المدعوم حالياً
            payload = {
                "model": "llama-3.1-8b-instant",  # تحديث الموديل من llama3-8b إلى llama-3.1-8b
                "messages": messages,
                "temperature": 0.6,               # تقليل الحرارة قليلاً لردود أكثر دقة
                "max_tokens": 800                 # زيادة عدد التوكنز للردود العربية الطويلة
            }

            response = await client.post(
                url, 
                json=payload, 
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code == 200:
                res_data = response.json()
                reply = res_data["choices"][0]["message"]["content"]
                
                # 2. محاكاة وقت "الكتابة" (0.05 ثانية لكل حرف بحد أقصى 3 ثواني)
                typing_time = min(len(reply) * 0.05, 3.0)
                await asyncio.sleep(typing_time)
                
                return reply
            
            # التعامل مع أخطاء الـ API (مثل انتهاء الرصيد أو الموديل)
            else:
                error_info = response.json()
                logger.error(f"❌ Groq API Error: {response.status_code} - {error_info}")
                return "المعذرة منك، يبدو أن هناك ضغط بسيط على النظام. كيف أقدر أساعدك بشيء آخر؟"
                
        except Exception as e:
            logger.error(f"❌ Critical Error in AI module: {str(e)}")
            return "يا هلا بك، حصل عندي عطل بسيط. ممكن تعيد إرسال رسالتك؟"

# --- خدمات واتساب (WhatsApp Business API) ---

# ... (نفس التعريفات السابقة) ...

# تعديل دالة send_whatsapp_dynamic لتستخدم الـ Web Bridge
async def send_whatsapp_dynamic(store_id: str, phone: str, text: str):
    """
    محاولة الإرسال عبر المتصفح المفتوح (Web Bridge).
    إذا لم يكن المتصفح جاهزاً، يتم تسجيل خطأ.
    """
    try:
        logger.info(f"Sending message to {phone} via Web Bridge...")
        await send_via_web_bridge(phone, text)
    except Exception as e:
        logger.error(f"Failed to send via Web Bridge: {str(e)}")

# تحسين دالة send_via_web_bridge لتكون أكثر ذكاءً
async def send_via_web_bridge(store_id: str, phone: str, text: str):
    """
    يرسل الرسالة عبر Baileys API مباشرة
    """
    handler = await get_handler_for_store(store_id)
    success = await handler.send_text(phone, text)
    if success:
        logger.info(f"✅ تم الإرسال للمتجر {store_id} عبر Baileys")
        return True
    return False

async def get_merchant_stats(store_id: str):
    """جلب إحصائيات المتجر من سلة باستخدام PostgreSQL لجلب التوكن"""
    try:
        # 1. جلب التوكن مباشرة من قاعدة البيانات
        query = "SELECT salla_access_token FROM store_settings WHERE store_id = :sid LIMIT 1"
        row = execute_db_query(query, {"sid": store_id}, fetch="one")
        
        if not row:
            logger.error(f"❌ لم يتم العثور على توكن للمتجر {store_id}")
            return {"orders": None, "abandoned_carts_count": 0}

        token = row[0]
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

        async with httpx.AsyncClient() as client:
            # 2. جلب إحصائيات الطلبات
            orders_resp = await client.get("https://api.salla.dev/admin/v2/reports/orders", headers=headers)
            
            # 3. جلب السلال المتروكة
            abandoned_resp = await client.get("https://api.salla.dev/admin/v2/abandoned-carts", headers=headers)

            # 4. التعامل مع احتمالية انتهاء التوكن (401)
            if orders_resp.status_code == 401 or abandoned_resp.status_code == 401:
                logger.info(f"🔄 تجديد التوكن للمتجر {store_id} أثناء جلب الإحصائيات...")
                new_token = await refresh_salla_token(store_id)
                if new_token:
                    # إعادة المحاولة بالتوكن الجديد
                    headers["Authorization"] = f"Bearer {new_token}"
                    orders_resp = await client.get("https://api.salla.dev/admin/v2/reports/orders", headers=headers)
                    abandoned_resp = await client.get("https://api.salla.dev/admin/v2/abandoned-carts", headers=headers)

            # 5. استخراج البيانات بأمان
            orders_data = orders_resp.json().get("data") if orders_resp.status_code == 200 else None
            
            abandoned_count = 0
            if abandoned_resp.status_code == 200:
                abandoned_count = abandoned_resp.json().get("pagination", {}).get("total", 0)

            return {
                "orders": orders_data,
                "abandoned_carts_count": abandoned_count
            }

    except Exception as e:
        logger.error(f"❌ خطأ في get_merchant_stats للمتجر {store_id}: {e}")
        return {"orders": None, "abandoned_carts_count": 0}
        
async def close_inactive_stores(max_idle_time=3600):
    """إغلاق صفحات المتاجر التي لم ترسل رسائل منذ ساعة لتوفير الرام"""
    # يمكنك إضافة منطق تسجيل وقت آخر نشاط لكل store_id في قاموس
    pass


async def send_admin_alert(store_id: str, customer_phone: str, last_message: str):
    """إرسال تنبيه لمالك المتجر عبر PostgreSQL عند الحاجة لتدخل بشري"""
    try:
        # 1. جلب رقم جوال الآدمن مباشرة من قاعدة البيانات
        query = "SELECT admin_phone FROM store_settings WHERE store_id = :sid LIMIT 1"
        row = execute_db_query(query, {"sid": store_id}, fetch="one")

        # 2. التحقق من وجود رقم المسجّل
        if not row or not row[0]:
            logger.warning(f"⚠️ تنبيه: لم يتم العثور على رقم أدمن للمتجر {store_id}")
            return

        admin_phone = row[0]
        
        # 3. صياغة نص التنبيه بشكل احترافي
        alert_text = (
            f"🚨 *تنبيه تدخل بشري!*\n\n"
            f"🏪 *المتجر:* {store_id}\n"
            f"👤 *العميل:* {customer_phone}\n"
            f"💬 *آخر رسالة:* {last_message}\n\n"
            f"📥 يرجى الدخول للوحة التحكم للرد على العميل."
        )
        
        # 4. الإرسال عبر الواتساب (باستخدام نظام الـ Web Bridge الذي أعددته)
        # نستخدم Background Task لضمان عدم تأخير البوت الأساسي
        await send_whatsapp_dynamic(store_id, admin_phone, alert_text)
        
        logger.info(f"🔔 تم إرسال تنبيه تدخل بشري لآدمن المتجر {store_id}")

    except Exception as e:
        logger.error(f"❌ خطأ أثناء إرسال تنبيه الآدمن للمتجر {store_id}: {e}")

# --- خدمات سلة شات (Salla Chat API) ---

async def send_salla_chat(store_id: str, conversation_id: str, text: str):
    """إرسال رد مباشر إلى محادثة العميل داخل متجر سلة باستخدام PostgreSQL"""
    try:
        # 1. جلب التوكن الحالي من قاعدة البيانات مباشرة
        query = "SELECT salla_access_token FROM store_settings WHERE store_id = :sid LIMIT 1"
        row = execute_db_query(query, {"sid": store_id}, fetch="one")
        
        if not row:
            logger.error(f"❌ تعذر العثور على توكن للمتجر {store_id} لإرسال الشات.")
            return

        token = row[0]
        url = f"https://api.salla.dev/admin/v2/chats/{conversation_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            # 2. محاولة إرسال الرسالة
            resp = await client.post(url, json={"message": text}, headers=headers)
            
            # 3. معالجة انتهاء صلاحية التوكن (401)
            if resp.status_code == 401:
                logger.info(f"🔄 توكن المتجر {store_id} منتهي، جاري التجديد لإرسال الشات...")
                new_token = await refresh_salla_token(store_id)
                if new_token:
                    headers["Authorization"] = f"Bearer {new_token}"
                    resp = await client.post(url, json={"message": text}, headers=headers)
            
            # 4. التحقق من نجاح الإرسال
            if resp.status_code in [200, 201]:
                logger.info(f"✅ تم إرسال الرد بنجاح لشات سلة (المحادثة: {conversation_id})")
            else:
                logger.error(f"⚠️ فشل إرسال شات سلة [{resp.status_code}]: {resp.text}")

    except Exception as e:
        logger.error(f"❌ خطأ في دالة send_salla_chat: {str(e)}")


async def check_abandoned_carts_and_remind(store_id: str):
    """البحث عن السلال المتروكة وإرسال تذكير عبر PostgreSQL لمنع التكرار"""
    try:
        # 1. جلب بيانات السلال المتروكة من سلة (باستخدام الدالة الموحدة المحدثة)
        carts_data = await salla_request("GET", "abandoned-carts", store_id)

  # --- اضفه هنا لترى الرد الكامل من سلة في Terminal ---
        print(f"\n--- DEBUG: Salla API Response for Store {store_id} ---")
        print(carts_data) 
        print("---------------------------------------------------\n")

        if not carts_data or "data" not in carts_data:
            logger.info(f"Empty abandoned carts for store {store_id}")
            return

        for cart in carts_data["data"]:
            cart_id = str(cart["id"])
            
            # 2. التحقق عبر SQL إذا كان العميل قد استلم تذكيراً لهذه السلة سابقاً
            check_query = "SELECT id FROM reminders_log WHERE cart_id = :cid LIMIT 1"
            already_reminded = execute_db_query(check_query, {"cid": cart_id}, fetch="one")
            
            if not already_reminded:
                customer_phone = cart["customer"]["mobile"]
                customer_name = cart["customer"]["first_name"]
                cart_url = cart.get("checkout_url")
                
                # صياغة الرسالة
                reminder_text = (
                    f"يا هلا يا {customer_name} 🌹،\n\n"
                    f"لاحظنا إنك تركت بعض المنتجات الرائعة في سلتك بمتجرنا. "
                    f"حبينا نذكرك إنها لسه بانتظارك وممكن تنفد في أي وقت!\n\n"
                    f"بإمكانك إكمال طلبك مباشرة من هنا:\n{cart_url}\n\n"
                    f"إذا واجهت أي مشكلة، أنا هنا لمساعدتك."
                )
                
                # 3. وضع الرسالة في طابور الإرسال (واتساب ويب)
                # نمرر store_id لضمان الإرسال من متصفح المتجر الصحيح
                await message_queue.put((store_id, customer_phone, reminder_text))
                
                # 4. تسجيل التذكير في PostgreSQL لضمان عدم التكرار
                insert_query = """
                    INSERT INTO reminders_log (cart_id, store_id, customer_phone, sent_at)
                    VALUES (:cid, :sid, :phone, NOW())
                """
                execute_db_query(insert_query, {
                    "cid": cart_id,
                    "sid": store_id,
                    "phone": customer_phone
                })
                
                logger.info(f"✅ تم تسجيل تذكير جديد للسلة {cart_id} للمتجر {store_id}")
                
                # انتظار بسيط لتجنب الحظر وتخفيف الضغط على المعالج
                await asyncio.sleep(2)

    except Exception as e:
        logger.error(f"❌ خطأ في دالة السلال المتروكة للمتجر {store_id}: {e}")

async def cron_scheduler():
    """مهمة تعمل في الخلفية كل ساعة لفحص السلال المتروكة"""
    while True:
        logger.info("Starting abandoned carts check cycle...")
        
        try:
            # الاتصال بقاعدة البيانات باستخدام الرابط الموحد
            conn = psycopg2.connect(os.getenv("DATABASE_URL"))
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # جلب المتاجر النشطة
            cur.execute("SELECT store_id FROM store_settings WHERE is_active = True")
            active_stores = cur.fetchall()
            
            # إغلاق الاتصال بعد جلب البيانات لتوفير موارد السيرفر
            cur.close()
            conn.close()

            # الدوران على المتاجر
            for store in active_stores:
                try:
                    await check_abandoned_carts_and_remind(store["store_id"])
                except Exception as e:
                    logger.error(f"Error in cron for store {store['store_id']}: {e}")
        
        except Exception as db_error:
            logger.error(f"Database connection error in cron: {db_error}")

        # الانتظار لمدة ساعة
        await asyncio.sleep(3600)
# تحديث دالة بدء التطبيق لتشغيل المجدل
@app.on_event("startup")
async def startup_event():
    # 1. تشغيل عامل إرسال الرسائل (مهم جداً لمعالجة الطابور)
    asyncio.create_task(message_worker())
    
    # 2. تشغيل مجدول السلال المتروكة
    asyncio.create_task(cron_scheduler())
    
    # 3. إزالة استدعاء ensure_browser_ready العام
    # السبب: الدالة الآن تتطلب store_id لفتح الجلسة من قاعدة البيانات.
    # المتصفح سيفتح تلقائياً "عند الحاجة" (On Demand) بمجرد وصول أول رسالة أو طلب إرسال.
    
    logger.info("🚀 تم تشغيل الخدمات الخلفية. المتصفح سيعمل تلقائياً عند وصول أول طلب لمتجر.")

# --- معالجة الـ Webhooks ---

# --- معالجة الـ Webhooks الموحدة والمصححة ---

@app.post("/webhook/whatsapp")
async def handle_whatsapp(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        
        # استخراج القيمة الأساسية (Value) من بيانات Meta
        value = data.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {})
        
        if 'messages' not in value:
            return {"status": "ignored"}

        # 1. تحديد المتجر بناءً على معرف رقم الهاتف (Phone Number ID)
        # هذا المعرف ثابت لكل رقم واتساب مربوط بـ Meta، وهو الأفضل للبحث في قاعدة البيانات
        phone_number_id = value.get('metadata', {}).get('phone_number_id')
        
        # 2. جلب الـ store_id من قاعدة البيانات (مثلاً Supabase أو Redis)
        # سنقوم هنا باستدعاء دالة تبحث عن المتجر المرتبط بهذا الـ phone_number_id
        store_id = await get_store_id_by_phone_id(phone_number_id)
        
        if not store_id:
            logger.warning(f"Unknown store for Phone ID: {phone_number_id}")
            return {"status": "error", "reason": "unregistered_number"}

        # 3. استخراج بيانات الرسالة
        msg_obj = value['messages'][0]
        customer_phone = msg_obj.get('from')
        text = msg_obj.get('text', {}).get('body', '').strip()
        
        if not text:
            return {"status": "ignored"}

        # 4. إرسال المهمة للخلفية مع معرف المتجر الصحيح
        background_tasks.add_task(process_customer_request, store_id, customer_phone, text)

        return {"status": "request_queued"}

    except Exception as e:
        logger.error(f"Critical Webhook Error: {str(e)}")
        return {"status": "error"}

# --- 1. دالة البحث عن المنتجات في سلة (المحرك الجديد) ---
async def search_salla_products(query: str, store_id: str) -> str:
    """البحث المباشر في API سلة لجلب بيانات المنتج الحالية"""
    try:
        # استخدام الكلمة المفتاحية المستخرجة من الذكاء الاصطناعي للبحث
        endpoint = f"products?keyword={query}"
        data = await salla_request("GET", endpoint, store_id)
        
        if not data or not data.get("data"):
            return f"عذراً، بحثت في المتجر ولم أجد منتجاً باسم '{query}' حالياً."

        # جلب أول نتيجة مطابقة (الأكثر دقة)
        p = data["data"][0]
        name = p.get("name")
        price = p.get("price", {}).get("amount")
        currency = p.get("price", {}).get("currency", "ر.س")
        link = p.get("urls", {}).get("customer")
        is_available = "متوفر" if p.get("is_available") else "غير متوفر حالياً"
        
        # تنظيف الوصف من أي وسوم HTML
        import re
        raw_desc = p.get("description", "لا يوجد وصف")
        clean_desc = re.sub('<[^<]+?>', '', raw_desc)[:120] # أول 120 حرف فقط

        return (
            f"معلومات المنتج الموجودة في المتجر:\n"
            f"- الاسم: {name}\n"
            f"- السعر: {price} {currency}\n"
            f"- الحالة: {is_available}\n"
            f"- وصف: {clean_desc}...\n"
            f"- الرابط المباشر: {link}"
        )
    except Exception as e:
        logger.error(f"Error searching products: {e}")
        return "حدث خطأ أثناء محاولة البحث عن تفاصيل المنتج."

# --- 2. تحديث محلل النية (Intent Analyzer) ليدعم المنتجات ---
# --- 3. المعالج الرئيسي المحدث (process_customer_request) ---
async def process_customer_request(store_id: str, phone: str, text: str):
    """المعالج الرئيسي المحدث: يدعم الاستعلام عن الطلبات والبحث عن المنتجات"""
    try:
        # 1. التحقق من حالة المتجر (SQL مباشر)
        store_query = "SELECT is_active, system_prompt FROM store_settings WHERE store_id = :sid LIMIT 1"
        store_res = execute_db_query(store_query, {"sid": store_id}).fetchone()
        
        if not store_res or not store_res[0]: 
            return
        
        system_prompt = store_res[1]

        # 2. إدارة هوية العميل (UPSERT)
        cust_query = """
            INSERT INTO customers (phone_number) VALUES (:phone)
            ON CONFLICT (phone_number) DO UPDATE SET phone_number = EXCLUDED.phone_number
            RETURNING id
        """
        cust_id = execute_db_query(cust_query, {"phone": phone}).fetchone()[0]

        # 3. حفظ رسالة العميل الواردة
        insert_msg_query = """
            INSERT INTO conversations (customer_id, role, content, created_at) 
            VALUES (:cid, 'user', :content, NOW())
        """
        execute_db_query(insert_msg_query, {"cid": cust_id, "content": text})

        # 4. تحليل النية عبر Groq
        analysis = await groq_analyze_intent(text)
        extra_info = ""

        # جلب المعلومات الخارجية بناءً على تحليل النية
        if analysis.get("is_order") and analysis.get("order_id"):
            extra_info = await get_salla_order(analysis["order_id"], store_id)
        elif analysis.get("is_product") and analysis.get("product_name"):
            extra_info = await search_salla_products(analysis["product_name"], store_id)

        # 5. جلب تاريخ المحادثة (ضروري لتوليد رد متناسق)
        history_query = """
            SELECT role, content FROM conversations 
            WHERE customer_id = :cid 
            ORDER BY created_at DESC LIMIT 5
        """
        history_rows = execute_db_query(history_query, {"cid": cust_id}).fetchall()
        # ترتيب الرسائل من الأقدم للأحدث ليقرأها الذكاء الاصطناعي بشكل صحيح
        history = [{"role": row[0], "content": row[1]} for row in reversed(history_rows)]

        # 6. توليد الرد باستخدام Groq (نمرر السياق الإضافي هنا)
        reply = await groq_generate_reply(history, extra_info, system_prompt)

        # 7. منطق التدخل البشري
        if "[HUMAN_REQUIRED]" in reply or any(word in text for word in ["موظف", "بشري", "حولني"]):
            human_msg = "أبشر، بحولك الآن لزميلي الموظف يكمل معك. لحظات ويكون معك."
            await message_queue.put((store_id, phone, human_msg))
            await send_admin_alert(store_id, phone, text)
            
            # تسجيل طلب التحويل في قاعدة البيانات
            execute_db_query(insert_msg_query, {"cid": cust_id, "content": "human_transfer_triggered"})
            return

        # 8. حفظ رد البوت وإرساله للعميل
        insert_bot_msg = """
            INSERT INTO conversations (customer_id, role, content, created_at) 
            VALUES (:cid, 'assistant', :content, NOW())
        """
        execute_db_query(insert_bot_msg, {"cid": cust_id, "content": reply})
        
        # وضع الرسالة في طابور الإرسال عبر الواتساب ويب
        await message_queue.put((store_id, phone, reply))

    except Exception as e:
        logger.error(f"Error in process_customer_request: {str(e)}")



@app.api_route("/webhook/salla", methods=["GET", "POST"]) # تعديل هنا للسماح بـ GET و POST
async def handle_salla_event(request: Request, background_tasks: BackgroundTasks):
    # 1. حل مشكلة الـ GET: إذا كان الطلب GET رُد بنجاح فوراً
    if request.method == "GET":
        return {"status": "ok", "message": "Webhook is active"}

    signature = request.headers.get("X-Salla-Signature")
    payload = await request.body()
    secret = os.getenv("SALLA_WEBHOOK_SECRET")
    
    if not verify_salla_signature(payload, signature, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = json.loads(payload)
    event = data.get("event")
    store_id = data.get("merchant")

    # 1. تحديث حالة الاشتراك
    if event == "app.subscription.started":
        query = "UPDATE store_settings SET is_active = True WHERE store_id = :sid"
        execute_db_query(query, {"sid": store_id})
    elif event == "app.subscription.expired":
        query = "UPDATE store_settings SET is_active = False WHERE store_id = :sid"
        execute_db_query(query, {"sid": store_id})

    # 2. تتبع الأرباح المستردة (ROI)
    if event == "order.created":
        order_data = data.get("data", {})
        customer_phone = order_data.get("customer", {}).get("mobile")
        order_total = order_data.get("total", {}).get("amount")
        
        # البحث عن آخر تذكير في آخر 24 ساعة باستخدام SQL
        check_query = """
            SELECT id FROM reminders_log 
            WHERE customer_phone = :phone AND store_id = :sid 
            AND sent_at > NOW() - INTERVAL '24 hours'
            ORDER BY sent_at DESC LIMIT 1
        """
        recent_reminder = execute_db_query(check_query, {"phone": customer_phone, "sid": store_id}, fetch="one")
            
        if recent_reminder:
            # تحديث السجل لإثبات أن البيعة تمت بفضل البوت
            update_query = """
                UPDATE reminders_log SET 
                is_recovered = True, recovered_amount = :amount, recovered_at = NOW()
                WHERE id = :rid
            """
            execute_db_query(update_query, {"amount": order_total, "rid": recent_reminder[0]})
            logger.info(f"💰 مبيعات مستردة بقيمة {order_total} للمتجر {store_id}")

    # 3. تسليم المنتجات الرقمية
    elif event == "order.updated":
        order_data = data.get("data", {})
        if order_data.get("status", {}).get("id") == 21: # "تم التنفيذ"
            digital_contents = []
            for item in order_data.get("items", []):
                for code in item.get("codes", []): 
                    digital_contents.append(f"🔑 كود {item['name']}: {code['code']}")
                for file in item.get("files", []): 
                    digital_contents.append(f"📁 ملف {item['name']}: {file['url']}")

            if digital_contents:
                delivery_msg = f"🎉 *تم تنفيذ طلبك #{order_data.get('id')}*\n\n" + "\n".join(digital_contents)
                background_tasks.add_task(message_queue.put, (store_id, order_data.get("customer", {}).get("mobile"), delivery_msg))

    # 4. معالجة الشات والذكاء الاصطناعي
    elif event == "chat.message.created":
        msg_data = data.get("data", {})
        if msg_data.get("type") == "sent_by_customer":
            phone = msg_data.get("customer", {}).get("mobile")
            text = msg_data.get("message")
            
            # حفظ/تحديث بيانات العميل وجلب الـ ID الخاص به في PostgreSQL
            cust_query = """
                INSERT INTO customers (phone_number, salla_customer_id, name)
                VALUES (:phone, :s_id, :name)
                ON CONFLICT (phone_number) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
            """
            cust_row = execute_db_query(cust_query, {
                "phone": phone, 
                "s_id": str(msg_data.get("customer_id")),
                "name": f"{msg_data.get('customer', {}).get('first_name', '')} {msg_data.get('customer', {}).get('last_name', '')}"
            }, fetch="one")
            
            cust_db_id = cust_row[0]

            # تسجيل رسالة العميل
            execute_db_query("INSERT INTO conversations (customer_id, role, content) VALUES (:cid, 'user', :txt)", 
                             {"cid": cust_db_id, "txt": text})
            
            # جلب إعدادات الرد وتاريخ المحادثة (آخر 5 رسائل)
            settings = execute_db_query("SELECT system_prompt FROM store_settings WHERE store_id = :sid", {"sid": store_id}, fetch="one")
            history_rows = execute_db_query("SELECT role, content FROM conversations WHERE customer_id = :cid ORDER BY created_at DESC LIMIT 5", 
                                            {"cid": cust_db_id}, fetch="all")
            history = [{"role": r[0], "content": r[1]} for r in reversed(history_rows)]

            # تحليل الرد عبر groq
            analysis = await groq_analyze_intent(text)
            context = await get_salla_order(analysis["order_id"], store_id) if analysis["order_id"] else ""
            reply = await groq_generate_reply(history, context, settings[0] if settings else "You are a helpful assistant")

            # التدخل البشري والرد
            if "[HUMAN_REQUIRED]" in reply or "موظف" in text:
                background_tasks.add_task(send_admin_alert, store_id, phone, text)
                reply = "تم تحويل طلبك للموظف المختص، سيتواصل معك قريباً."
            
            # تسجيل رد البوت وإرساله
            execute_db_query("INSERT INTO conversations (customer_id, role, content) VALUES (:cid, 'assistant', :txt)", 
                             {"cid": cust_db_id, "txt": reply})
            background_tasks.add_task(send_salla_chat, store_id, msg_data.get("conversation_id"), reply)

    return {"status": "ok"}


# تغيير من dashboard-stats إلى dashboard
@app.get("/api/dashboard/{store_id}") 
async def get_dashboard_api_data(store_id: str):

    """جلب كافة بيانات لوحة التحكم باستخدام PostgreSQL المباشر"""
    global browser_instance
    
    try:
        # 1. تحديد النطاق الزمني (آخر 7 أيام)
        today = datetime.now()
        last_week = today - timedelta(days=7)

        # 2. جلب سجلات الاسترداد الناجحة (الأرباح)
        rev_query = """
            SELECT recovered_amount, recovered_at 
            FROM reminders_log 
            WHERE store_id = :sid AND is_recovered = TRUE AND recovered_at >= :last_week
        """
        revenue_data = execute_db_query(rev_query, {"sid": store_id, "last_week": last_week}, fetch="all") or []
        
        # تجميع الأرباح
        total_revenue = sum(float(row[0] or 0) for row in revenue_data)

        # 3. معالجة بيانات الرسم البياني
        days_map = {}
        arabic_days = {
            "Saturday": "السبت", "Sunday": "الأحد", "Monday": "الاثنين", 
            "Tuesday": "الثلاثاء", "Wednesday": "الأربعاء", "Thursday": "الخميس", "Friday": "الجمعة"
        }
        
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            days_map[d.strftime('%A')] = 0

        for row in revenue_data:
            dt_val = row[1]
            if isinstance(dt_val, str):
                dt_obj = datetime.fromisoformat(dt_val.replace('Z', '+00:00'))
            else:
                dt_obj = dt_val
            
            d_name = dt_obj.strftime('%A')
            if d_name in days_map:
                days_map[d_name] += float(row[0] or 0)

        chart_labels = [arabic_days[d] for d in days_map.keys()]
        chart_values = list(days_map.values())

        # 4. جلب إحصائيات سلة والردود الآلية
        conv_count = execute_db_query("SELECT COUNT(id) FROM conversations WHERE role = 'assistant'", fetch="one")
        abandoned_res = execute_db_query("SELECT COUNT(id) FROM reminders_log WHERE store_id = :sid", {"sid": store_id}, fetch="one")

        # جلب أحدث عملية استرداد لإرسال التنبيه
        recent_recovery_query = """
            SELECT id, recovered_amount, customer_phone 
            FROM reminders_log 
            WHERE store_id = :sid AND is_recovered = TRUE 
            ORDER BY recovered_at DESC LIMIT 1
        """
        recent_recovery = execute_db_query(recent_recovery_query, {"sid": store_id}, fetch="one")
        recent_recoveries_list = []
        if recent_recovery:
            recent_recoveries_list.append({
                "id": recent_recovery[0], 
                "amount": float(recent_recovery[1]), 
                "phone": recent_recovery[2]
            })

        # 5. جلب آخر 10 محادثات مع ربط الجداول (JOIN)
        recent_chats_query = """
            SELECT c.id, c.customer_id, c.role, c.content, c.created_at, cu.phone_number 
            FROM conversations c 
            LEFT JOIN customers cu ON c.customer_id = cu.id 
            ORDER BY c.created_at DESC LIMIT 10
        """
        recent_chats_data = execute_db_query(recent_chats_query, fetch="all") or []
        recent_chats = [
            {
                "id": r[0], "customer_id": r[1], "role": r[2], "content": r[3], 
                "created_at": r[4], "customers": {"phone_number": r[5]}
            }
            for r in recent_chats_data
        ]

        # 6. فحص حالة المتصفح (Playwright)
        is_browser_alive = False
        try:
            if 'browser_instance' in globals() and browser_instance and browser_instance.is_connected():
                is_browser_alive = True
        except:
            is_browser_alive = False

        # 7. الرد النهائي
        return {
            "summary": {
                "total_revenue_saved": total_revenue
            },
            "recent_recoveries": recent_recoveries_list,
            "bot_usage": conv_count[0] if conv_count else 0,
            "salla_stats": {
                "abandoned_carts_count": abandoned_res[0] if abandoned_res else 0
            },
            "charts_data": {
                "labels": chart_labels,
                "values": chart_values
            },
            "recent_activity": recent_chats,
            "browser_connected": is_browser_alive
        }

    except Exception as e:
        logger.error(f"Dashboard Data Error: {str(e)}")
        return {"error": f"حدث خطأ أثناء تحديث البيانات: {str(e)}"}

@app.get("/admin/dashboard/{store_id}", response_class=HTMLResponse)
async def serve_dashboard(request: Request, store_id: str):
    try:
        # الحل: تمرير request مباشرة كأول وسيط للدالة
        return templates.TemplateResponse(
            request=request,  # تم نقله هنا ليكون وسيطاً صريحاً
            name="index.html",
            context={
                "store_id": str(store_id) # اترك القيم الأخرى هنا
            }
        )
    except Exception as e:
        error_msg = f"خطأ في معالجة القالب: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return HTMLResponse(content=f"<h1>{error_msg}</h1>", status_code=500)

@app.get("/admin/advanced-stats/{store_id}")
async def get_advanced_analytics(store_id: str):
    try:
        # 1. إجمالي السلال المتروكة التي تمت مراسلتها
        reminded_query = "SELECT COUNT(cart_id) FROM reminders_log WHERE store_id = :sid"
        reminded_carts = execute_db_query(reminded_query, {"sid": store_id}, fetch="one")
        total_reminders = reminded_carts[0] if reminded_carts else 0
        
        # 2. جلب الطلبات الناجحة التي تمت "بعد" إرسال تذكير
        success_query = "SELECT COUNT(cart_id) FROM reminders_log WHERE store_id = :sid AND is_recovered = TRUE"
        successful_recoveries = execute_db_query(success_query, {"sid": store_id}, fetch="one")
        total_recoveries = successful_recoveries[0] if successful_recoveries else 0

        # 3. حساب إجمالي الأرباح المستردة (باستخدام دالة التجميع SUM بدلاً من RPC لتكون أسرع وأضمن)
        revenue_query = "SELECT SUM(recovered_amount) FROM reminders_log WHERE store_id = :sid AND is_recovered = TRUE"
        total_revenue = execute_db_query(revenue_query, {"sid": store_id}, fetch="one")
        total_recovered_revenue = float(total_revenue[0] or 0)

        # 4. أداء الذكاء الاصطناعي (AI vs Human)
        ai_query = "SELECT COUNT(id) FROM conversations WHERE role = 'assistant'"
        ai_responses = execute_db_query(ai_query, fetch="one")
        total_ai_chats = ai_responses[0] if ai_responses else 0
            
        human_query = "SELECT COUNT(id) FROM conversations WHERE content = 'human_transfer_triggered'"
        human_requests = execute_db_query(human_query, fetch="one")
        total_human_reqs = human_requests[0] if human_requests else 0

        recovery_rate = (total_recoveries / total_reminders * 100) if total_reminders else 0
        human_rate = (total_human_reqs / total_ai_chats * 100) if total_ai_chats else 0

        return {
            "summary": {
                "total_reminders_sent": total_reminders,
                "recovered_carts_count": total_recoveries,
                "recovery_rate": f"{recovery_rate:.1f}%",
                "total_revenue_saved": total_recovered_revenue
            },
            "ai_performance": {
                "automated_chats": total_ai_chats,
                "human_intervention_rate": f"{human_rate:.1f}%"
            },
            "charts_data": {
                "labels": ["السبت", "الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة"],
                "data": [12, 19, 3, 5, 2, 3, 10]
            }
        }
    except Exception as e:
        logger.error(f"Analytics Error: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/admin/update-config/{store_id}")
async def update_config(store_id: str, settings: dict):
    """تحديث إعدادات المسؤول والبرومبت من لوحة التحكم"""
    try:
        query = """
            UPDATE store_settings 
            SET admin_phone = :phone, system_prompt = :prompt 
            WHERE store_id = :sid
        """
        execute_db_query(query, {
            "phone": settings.get("admin_phone"),
            "prompt": settings.get("system_prompt"),
            "sid": store_id
        })
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))






# 1. دالة الباركود

# 1. دالة جلب الباركود


# نفترض أن لديك كلاس لإدارة العمليات (Subprocess)
# إذا لم يكن لديك، سأضع لك لمحة عنه بالأسفل



@app.get("/api/whatsapp/get-qr/{store_id}")
async def fetch_qr(store_id: str):
    # استدعاء الدالة التي اختبرناها في Termux
    base64_qr = await get_qr_from_bridge(store_id)
    
    if base64_qr == "CONNECTED":
        return {"status": "success", "message": "المتجر متصل بالفعل ✅", "code": 200}
    
    if base64_qr:
        return {
            "status": "qr_ready",
            "qr_image": base64_qr,  # هذا هو الكود الذي سيوضع في وسم <img>
            "message": "تم توليد الباركود بنجاح"
        }
    
    return {"status": "error", "message": "فشل في توليد الباركود، حاول مجدداً"}

# 2. دالة كود الربط (Pairing Code)
@app.get("/admin/link-phone/{store_id}")
async def link_phone_auto_logic(store_id: str, phone: str):
    clean_phone = "".join(filter(str.isdigit, phone))
    instance_id = f"{store_id}_{clean_phone[-4:]}"
    print(f"\n{'='*50}\n📱 [BACKEND - PAIRING] بدء طلب كود ربط للجلسة: {instance_id}\n{'='*50}")
    
    whatsapp_url = os.getenv("WHATSAPP_URL", "").rstrip("/")
    api_key = os.getenv("WHATSAPP_API_KEY")
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    
    async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
        try:
            # --- الخطوة 1: الفحص ---
            status_url = f"{whatsapp_url}/instance/connectionState/{instance_id}"
            print(f"🔍 [1] فحص الجلسة: {status_url}")
            status_resp = await client.get(status_url, headers=headers)
            print(f"📥 [1] استجابة الفحص | الكود: {status_resp.status_code}")
            
            # --- الخطوة 2: الإنشاء ---
            if status_resp.status_code == 404:
                print(f"🏗️ [2] الجلسة غير موجودة. جاري الإنشاء للرقم: {clean_phone}")
                create_payload = {
                    "instanceName": instance_id,
                    "token": api_key,
                    "qrcode": False,
                    "number": clean_phone,
                    "integration": "WHATSAPP-BAILEYS"
                }
                create_url = f"{whatsapp_url}/instance/create"
                print(f"📡 [2] بيانات الإنشاء: {create_payload}")
                
                create_resp = await client.post(create_url, json=create_payload, headers=headers)
                print(f"📥 [2] استجابة الإنشاء | الكود: {create_resp.status_code} | النص: {create_resp.text}")
                
                if create_resp.status_code not in [200, 201]:
                    return {"status": "error", "message": f"فشل الإنشاء (الخطأ {create_resp.status_code}): {create_resp.text}"}
                
                print("⏳ [2] ننتظر 5 ثوانٍ لتهيئة الجلسة برقم الهاتف...")
                await asyncio.sleep(5.0)

            # --- الخطوة 3: طلب الكود ---
            connect_url = f"{whatsapp_url}/instance/connect/{instance_id}?number={clean_phone}"
            print(f"🔄 [3] جاري طلب كود الربط: {connect_url}")
            qr_resp = await client.get(connect_url, headers=headers)
            print(f"📥 [3] استجابة طلب الكود | الكود: {qr_resp.status_code}")
            
            if qr_resp.status_code == 200:
                data = qr_resp.json()
                pairing_code = data.get("code") or data.get("pairingCode")
                if pairing_code:
                    print(f"✅ [3] تم استلام كود الربط: {pairing_code}")
                    return {
                        "status": "success", 
                        "pairing_code": pairing_code, 
                        "instance_name": instance_id
                    }
                print(f"⚠️ [3] الكود غير متوفر في الرد: {data}")
            else:
                print(f"❌ [3] فشل طلب الكود | النص: {qr_resp.text}")
            
            return {"status": "error", "message": "فشل توليد الكود. قد تكون الجلسة مشغولة، جرب بعد ثوانٍ."}

        except Exception as e:
            print(f"🚨 [خطأ استثنائي] {str(e)}")
            return {"status": "error", "message": str(e)}

async def send_whatsapp_message(phone: str, message: str, store_id: str):
    # إعداد البيانات للـ Evolution API
    url = f"{WHATSAPP_URL}/message/sendText/{store_id}"
    headers = {
        "apikey": WHATSAPP_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "number": phone, # يجب أن يكون الرقم بالصيغة الدولية بدون +
        "options": {"delay": 1200, "presence": "composing"},
        "textMessage": {"text": message}
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 201:
            print("✅ تم إرسال الرسالة بنجاح")
            return True
        else:
            print(f"❌ فشل الإرسال: {response.text}")
            return False

# تأكد من استيراد هذا

@app.get("/callback")
async def salla_callback(code: str, state: str = None):
    """استقبال التاجر وتوجيهه للوحة التحكم مع معالجة المهلة والأخطاء"""
    token_url = "https://accounts.salla.sa/oauth2/token"
    user_info_url = "https://accounts.salla.sa/oauth2/user/info"
    
    redirect_uri = os.getenv("SALLA_CALLBACK_URL") 
    
    payload = {
        "client_id": os.getenv("SALLA_CLIENT_ID"),
        "client_secret": os.getenv("SALLA_CLIENT_SECRET"),
        "grant_type": "authorization_code",
        "code": code,
        "scope": "offline_access",
        "redirect_uri": redirect_uri,
    }
    
    # زيادة المهلة لـ 40 ثانية لضمان استجابة سلة وسرعة Render
    async with httpx.AsyncClient(timeout=40.0) as client:
        try:
            # 1. تبادل الكود بالتوكنات
            resp = await client.post(token_url, data=payload)
            
            if resp.status_code != 200:
                logger.error(f"❌ فشل تبادل التوكن: {resp.text}")
                return HTMLResponse(content=f"<h1>فشل الربط</h1><p>{resp.text}</p>", status_code=400)

            token_data = resp.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")

            # 2. جلب معلومات المتجر (بمهلة انتظار كافية)
            user_info_resp = await client.get(
                user_info_url, 
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if user_info_resp.status_code != 200:
                return HTMLResponse(content="<h1>فشل جلب بيانات المتجر</h1>", status_code=400)

            user_data = user_info_resp.json()
            
            # المسار الأكثر دقة للمعرف في سلة
            store_id = str(user_data["data"]["id"]) 
            store_name = user_data["data"].get("name", "متجرك")

            # 3. حفظ البيانات في PostgreSQL (تأكد من وجود الأعمدة في القاعدة)
            upsert_query = """
                INSERT INTO store_settings (store_id, salla_access_token, refresh_token, is_active, updated_at)
                VALUES (:sid, :access, :refresh, True, NOW())
                ON CONFLICT (store_id) DO UPDATE SET 
                    salla_access_token = EXCLUDED.salla_access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    is_active = True,
                    updated_at = NOW();
            """
            
            execute_db_query(upsert_query, {
                "sid": store_id,
                "access": access_token,
                "refresh": refresh_token
            })
            
            logger.info(f"🚀 تم الربط بنجاح للمتجر: {store_id} ({store_name})")
            
            # 4. التوجيه التلقائي للوحة التحكم
            return RedirectResponse(url=f"/admin/dashboard/{store_id}")
            
        except httpx.ReadTimeout:
            logger.error("⏳ انتهت مهلة الانتظار مع سيرفر سلة")
            return HTMLResponse("<h1>خطأ في الاتصال</h1><p>استغرق سيرفر سلة وقتاً طويلاً للرد. حاول مرة أخرى.</p>", status_code=504)
        except Exception as e:
            logger.error(f"❌ خطأ غير متوقع: {e}")
            return HTMLResponse(content=f"<h1>خطأ فني</h1><p>{str(e)}</p>", status_code=500)


@app.post("/admin/test-ai/{store_id}")
async def test_ai(store_id: str, data: dict):
    user_msg = data.get("message")
    system_prompt = data.get("prompt")
    
    try:
        # قمنا بتغيير get_ai_response إلى groq_generate_reply
        # ونمرر رسالة المستخدم كقائمة (History) كما تتوقع الدالة
        history = [{"role": "user", "content": user_msg}]
        
        # استدعاء دالة groq التي عرفتها في الأعلى
        reply = await groq_generate_reply(
            history=history, 
            context="اختبار من لوحة التحكم", 
            system_prompt=system_prompt
        )
        
        return {"reply": reply}
    except Exception as e:
        logger.error(f"Test AI Error: {str(e)}")
        return {"reply": f"خطأ في النظام: {str(e)}"}


# ... (بقية الكود الخاص بك) ...

@app.get("/", response_class=HTMLResponse)
async def read_index():
    # التأكد من وجود الملف قبل محاولة فتحه لتجنب انهيار السيرفر
    file_path = "index.html"
    if os.path.exists(file_path):
        return FileResponse(file_path)
    else:
        logger.error("❌ ملف index.html غير موجود في الجذر!")
        return HTMLResponse(content="<h1>خطأ: ملف واجهة المستخدم مفقود</h1>", status_code=404)

@app.get("/health")
def health_check():
    return {
        "status": "online", 
        "engine": "PostgreSQL (Internal)",
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "storage_check": os.path.exists("whatsapp_sessions") # التأكد من وجود مجلد الجلسات
    }

# إفادة Render بالمنفذ الصحيح (Port)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
