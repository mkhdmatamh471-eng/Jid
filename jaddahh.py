import os
import hmac
import hashlib
import tarfile
import base64
import io
import json
import logging
import asyncio
import random
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from playwright.async_api import async_playwright
import base64
import httpx
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from supabase import create_client, Client
from dotenv import load_dotenv
from pydantic import BaseModel
from datetime import datetime, timedelta
import logging
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta
import logging
from fastapi.responses import HTMLResponse
import psycopg2  
from psycopg2.extras import RealDictCursor
# إعداد الـ Logger لضمان ظهور الأخطاء في سجلات ريندر
logger = logging.getLogger(__name__)

app = FastAPI()

# إذا كان لديك ملفات CSS أو JS خارجية (اختياري)
# app.mount("/static", StaticFiles(directory="static"), name="static")


# تأكد من وجود المسارات التي يطلبها الـ JavaScript في ملفك


logger = logging.getLogger(__name__)


# قواميس لتخزين الجلسات والصفحات لكل متجر على حدة
contexts: Dict[str, any] = {} 
pages: Dict[str, any] = {}
browser_instance = None
# 1. الإعدادات والتحميل
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Salla AI Integrated Bot")

SESSION_PATH = os.path.join(os.getcwd(), "whatsapp_session")

# تكوين البيئة
SESSION_PATH = os.path.join(os.getcwd(), "whatsapp_sessions")

# تحميل ملف .env فقط إذا كان موجوداً (للتطوير المحلي)
# في ريندر، سيتم تجاهل هذا السطر واستخدام إعدادات البيئة المباشرة
load_dotenv()

# 1. جلب رابط قاعدة البيانات ومعالجة مشكلة "postgres://" في SQLAlchemy
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 2. جلب بقية المفاتيح
GROK_API_KEY = os.getenv("GROK_API_KEY")
# 3. إعدادات Salla (يفضل إضافتها أيضاً)
SALLA_CLIENT_ID = os.getenv("SALLA_CLIENT_ID")
SALLA_CLIENT_SECRET = os.getenv("SALLA_CLIENT_SECRET")
SALLA_WEBHOOK_SECRET = os.getenv("SALLA_WEBHOOK_SECRET")
engine = create_engine(
    DATABASE_URL,
    pool_size=10,          # عدد الاتصالات المفتوحة الجاهزة للاستخدام
    max_overflow=20,       # أقصى عدد اتصالات إضافية عند الضغط
    pool_pre_ping=True,    # التحقق من سلامة الاتصال قبل استخدامه
    pool_recycle=300       # إعادة تدوير الاتصال كل 5 دقائق
)

# إنشاء مصنع الجلسات
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def execute_db_query(query: str, params: dict = None):
    """
    دالة موحدة لتنفيذ استعلامات SQL بشكل آمن وسريع
    """
    try:
        with engine.connect() as connection:
            result = connection.execute(text(query), params or {})
            connection.commit() # ضروري لحفظ التغييرات (Insert/Update)
            return result
    except Exception as e:
        logger.error(f"Database Query Error: {e}")
        raise e        
message_queue = asyncio.Queue()

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

# تشغيل العامل عند بدء التطبيق

def verify_salla_signature(payload: bytes, signature: str, secret: str):
    computed_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_sig, signature)

# --- خدمات SALLA (Authentication & Data) ---
# نحتاج لتخزين كائن playwright لإغلاقه بشكل صحيح




# تحديد مسار حفظ بيانات الجلسة (سيتم إنشاء مجلد في نفس مسار السكربت)

async def get_handler_for_store(store_id: str):
    """جلب أو إنشاء صفحة واتساب مع استعادة الجلسة من قاعدة البيانات"""
    global browser_instance, pages, contexts
    
    # 1. تشغيل المحرك الرئيسي (مرة واحدة فقط)
    if not browser_instance or not browser_instance.is_connected():
        # ملاحظة: عند استخدام launch_persistent_context لاحقاً، 
        # المتصفح والسياق يندمجان، لكننا نحتاج لمحرك Playwright أولاً
        from playwright.async_api import async_playwright
        playwright_manager = await async_playwright().start()

    # 2. التحقق مما إذا كانت الصفحة مفتوحة ونشطة
    if store_id in pages and not pages[store_id].is_closed():
        try:
            await pages[store_id].evaluate("1+1")
            return pages[store_id]
        except:
            logger.warning(f"🔄 صفحة المتجر {store_id} لا تستجيب، إعادة تهيئة...")

    # 3. إدارة الجلسة (الاستعادة من قاعدة البيانات)
    storage_path = os.path.join(SESSION_PATH, f"session_{store_id}")
    
    # إذا لم يكن المجلد موجوداً محلياً (مثلاً بعد ريستارت لريندر)
    if not os.path.exists(storage_path):
        logger.info(f"📥 محاولة استعادة جلسة المتجر {store_id} من Supabase...")
        success = await load_session_from_db(store_id)
        if not success:
            os.makedirs(storage_path, exist_ok=True)
            logger.info(f"🆕 لا توجد جلسة سابقة، سيتم إنشاء مجلد جديد.")

    # 4. تشغيل المتصفح بنظام الـ Persistent Context
    # هذا النظام يربط المجلد بالمتصفح مباشرة لحفظ التغييرات
    try:
        context = await playwright_manager.chromium.launch_persistent_context(
            user_data_dir=storage_path,
            headless=True,
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ],
            viewport={'width': 800, 'height': 600},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."
        )
        
        # في نظام الـ Persistent Context، يتم فتح صفحة تلقائياً، نستخدمها أو نفتح واحدة
        page = context.pages[0] if context.pages else await context.new_page()

        # 5. تحسين الأداء (منع الصور والوسائط)
        await page.route("**/*", block_useless_resources)

        # 6. التوجه لواتساب ويب
        await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=90000)
        
        # 7. حقن المراقب
        await setup_inbound_observer(page, store_id)

        # تخزين المراجع
        pages[store_id] = page
        contexts[store_id] = context
        
        logger.info(f"✅ صفحة المتجر {store_id} جاهزة.")
        return page

    except Exception as e:
        logger.error(f"❌ خطأ أثناء تشغيل متصفح المتجر {store_id}: {e}")
        return None


# دالة منفصلة لمعالجة المنطق لتجنب التعقيد داخل ensure_browser_ready

async def ensure_browser_ready(store_id: str):
    """
    تتأكد من جاهزية المتصفح للمتجر المحدد.
    تقوم بتحميل الجلسة من قاعدة البيانات إذا لم تكن موجودة محلياً.
    """
    global playwright_manager, browser_instance, contexts, pages

    try:
        # 1. التأكد من وجود المجلد الرئيسي للجلسات
        if not os.path.exists(SESSION_PATH):
            os.makedirs(SESSION_PATH)

        # 2. بدء محرك Playwright إذا لم يكن يعمل
        if playwright_manager is None:
            playwright_manager = await async_playwright().start()
            logger.info("🚀 تم تشغيل محرك Playwright بنجاح")

        # 3. تحديد مسار الجلسة الخاص بهذا المتجر
        storage_path = os.path.join(SESSION_PATH, f"session_{store_id}")

        # 4. استعادة الجلسة من قاعدة البيانات (إذا كانت مفقودة محلياً)
        if not os.path.exists(storage_path):
            logger.info(f"📥 الجلسة مفقودة محلياً للمتجر {store_id}، جاري محاولة التحميل من Supabase...")
            # دالة load_session_from_db هي التي تقوم بفك الضغط في storage_path
            await load_session_from_db(store_id)

        # 5. تشغيل المتصفح بنظام Persistent Context (يربط المجلد بالمتصفح مباشرة)
        # نتحقق مما إذا كان السياق الخاص بالمتجر موجوداً ومفتوحاً
        if store_id not in contexts or not browser_instance.is_connected():
            logger.info(f"🌐 فتح متصفح جديد للمتجر: {store_id}")
            
            context = await playwright_manager.chromium.launch_persistent_context(
                user_data_dir=storage_path,
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ],
                viewport={'width': 800, 'height': 600},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            contexts[store_id] = context
            # فتح صفحة جديدة أو استخدام الصفحة الافتراضية
            pages[store_id] = context.pages[0] if context.pages else await context.new_page()
            
            # إعداد حظر الصور لتوفير الرام
            await pages[store_id].route("**/*", block_useless_resources)
            
            logger.info(f"✅ المتصفح جاهز الآن للمتجر {store_id}")
        
        return pages[store_id]

    except Exception as e:
        logger.error(f"❌ فشل في ensure_browser_ready للمتجر {store_id}: {e}")
        return None

async def save_session_to_db(store_id: str):
    """ضغط مجلد الجلسة ورفعه إلى سوبابيس"""
    try:
        path = os.path.join(SESSION_PATH, f"session_{store_id}")
        if not os.path.exists(path): return

        # ضغط المجلد في الذاكرة
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            tar.add(path, arcname=os.path.basename(path))
        
        # تحويل لـ Base64
        b64_session = base64.b64encode(buffer.getvalue()).decode()
        
        # حفظ في سوبابيس
        supabase.table("store_sessions").upsert({
            "store_id": store_id,
            "session_data": b64_session,
            "updated_at": datetime.now().isoformat()
        }).execute()
        
        logger.info(f"✅ تم حفظ جلسة المتجر {store_id} في قاعدة البيانات.")
    except Exception as e:
        logger.error(f"❌ خطأ أثناء حفظ الجلسة: {e}")

async def load_session_from_db(store_id: str):
    """تحميل الجلسة من قاعدة البيانات وفك ضغطها"""
    try:
        res = supabase.table("store_sessions").select("session_data").eq("store_id", store_id).execute()
        if not res.data: return False

        b64_data = res.data[0]["session_data"]
        compressed_data = base64.b64decode(b64_data)
        
        # فك الضغط في المسار المطلوب
        buffer = io.BytesIO(compressed_data)
        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            tar.extractall(path=SESSION_PATH)
        
        logger.info(f"📂 تم استعادة جلسة المتجر {store_id} من قاعدة البيانات.")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ أثناء تحميل الجلسة: {e}")
        return False
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
                    # هنا نربط مع دالة Grok التي كتبناها سابقاً
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

async def setup_inbound_observer(page, store_id: str):
    """حقن كود مراقبة الرسائل لاستخراج البيانات بدقة لكل متجر"""
    
    # 1. تعريف الدالة التي تستقبل البيانات من المتصفح (JavaScript -> Python)
    async def on_message_received(payload):
        phone = payload.get("phone")
        text = payload.get("text")
        
        logger.info(f"📩 [المتجر: {store_id}] رسالة من {phone}: {text}")
        
        if text and phone:
            # تشغيل المعالجة في الخلفية (Grok AI) لضمان عدم تعليق المتصفح
            asyncio.create_task(process_customer_request(store_id, phone, text))
    
    # 2. ربط الدالة بالمتصفح لكي يتمكن الـ JS من مناداتها
    await page.expose_function("notifyNewMessage", on_message_received)

    # 3. حقن كود الـ JavaScript داخل المتصفح (الـ MutationObserver)
    await page.evaluate("""
        const observer = new MutationObserver((mutations) => {
            // البحث عن دوائر الإشعارات غير المقروءة في القائمة الجانبية
            const unread = document.querySelector('span[aria-label*="unread"], span[aria-label*="غير مقروءة"]');
            
            if (unread) {
                // الوصول لصف المحادثة (الـ Row) الذي يحتوي على الإشعار
                const chatRow = unread.closest('div[role="row"]');
                if (chatRow) {
                    // استخراج الاسم أو الرقم من خاصية title
                    const titleEl = chatRow.querySelector('span[title]');
                    const contact = titleEl ? titleEl.getAttribute('title') : "Unknown";
                    
                    // استخراج آخر نص رسالة ظاهر في القائمة (Selectors مرنة لضمان الاستمرارية)
                    const msgEl = chatRow.querySelector('span._ao3e, span[dir="ltr"]'); 
                    const lastMsg = msgEl ? msgEl.innerText : "";

                    // إرسال البيانات فوراً إلى دالة البايثون
                    window.notifyNewMessage({
                        phone: contact,
                        text: lastMsg
                    });
                }
            }
        });
        
        // تشغيل المراقب على القائمة الجانبية فقط (توفيراً للرام)
        const sideBar = document.querySelector('#pane-side');
        if (sideBar) {
            observer.observe(sideBar, { childList: true, subtree: true });
            console.log("✅ MutationObserver active for store");
        }
    """)

async def block_useless_resources(route):
    # قائمة بالموارد التي لا يحتاجها البوت لأداء مهامه البرمجية
    useless_types = ["image", "media", "font", "manifest", "other"]
    
    if route.request.resource_type in useless_types:
        await route.abort()
    else:
        # يمكنك أيضاً حظر روابط معينة مثل التحليلات (Analytics) لتسريع الأداء
        url = route.request.url
        if "google-analytics" in url or "facebook" in url:
            await route.abort()
        else:
            await route.continue_()

# الاستخدام داخل الكود
# await page.route("**/*", block_useless_resources)

# داخل دالة فتح الصفحة


async def salla_request(method: str, endpoint: str, store_id: str, payload: dict = None):
    """دالة موحدة لطلبات سلة مع تجديد تلقائي للتوكن"""
    res = supabase.table("store_settings").select("salla_access_token").eq("store_id", store_id).single().execute()
    token = res.data["salla_access_token"]
    
    url = f"https://api.salla.dev/admin/v2/{endpoint}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    
    async with httpx.AsyncClient() as client:
        if method.upper() == "GET":
            resp = await client.get(url, headers=headers)
        else:
            resp = await client.post(url, headers=headers, json=payload)
            
        if resp.status_code == 401: # التوكن انتهى
            new_token = await refresh_salla_token(store_id)
            if new_token:
                headers["Authorization"] = f"Bearer {new_token}"
                # إعادة المحاولة بالتوكن الجديد
                return await salla_request(method, endpoint, store_id, payload)
        
        return resp.json() if resp.status_code == 200 else None

async def refresh_salla_token(store_id: str) -> Optional[str]:
    """تجديد توكن سلة تلقائياً عند انتهائه"""
    res = supabase.table("store_settings").select("*").eq("store_id", store_id).single().execute()
    if not res.data: return None
    
    s = res.data
    url = "https://accounts.salla.sa/oauth2/token"
    payload = {
        "client_id": s["client_id"],
        "client_secret": s["client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": s["refresh_token"]
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=payload)
        if resp.status_code == 200:
            data = resp.json()
            supabase.table("store_settings").update({
                "salla_access_token": data["access_token"],
                "refresh_token": data["refresh_token"]
            }).eq("store_id", store_id).execute()
            return data["access_token"]
    return None

async def get_salla_order(order_id: str, store_id: str) -> Optional[str]:
    """جلب بيانات الطلب مع محاولة تجديد التوكن إذا لزم الأمر"""
    res = supabase.table("store_settings").select("salla_access_token").eq("store_id", store_id).single().execute()
    token = res.data["salla_access_token"]
    
    url = f"https://api.salla.dev/admin/v2/orders/{order_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 401: # Token Expired
            token = await refresh_salla_token(store_id)
            if token:
                headers["Authorization"] = f"Bearer {token}"
                resp = await client.get(url, headers=headers)
        
        if resp.status_code == 200:
            d = resp.json()["data"]
            return f"طلب {d['reference_id']}: حالة {d['status']['name']}, تتبع: {d['shipping'].get('tracking_link', 'قريباً')}"
    return None

# --- خدمات الذكاء الاصطناعي (GROK xAI) ---

async def grok_analyze_intent(message: str) -> Dict:
    """استخراج نية العميل ورقم الطلب باستخدام Grok بدقة وموثوقية عالية"""
    url = "https://api.x.ai/v1/chat/completions"
    
    # البرومبت المطور لضمان الدقة واستخراج الأرقام بشكل صحيح
    prompt = """
    حلل رسالة العميل التالية واستخرج النية (Intent) ورقم الطلب إن وجد.
    يجب أن يكون الرد بصيغة JSON فقط، بدون أي نص إضافي قبل أو بعد القوسين، وبدون علامات Markdown.

    القواعد:
    1. is_order: تكون true إذا كان العميل يستفسر عن حالة طلب، تتبع شحنة، أو تعديل طلب.
    2. order_id: استخرج رقم الطلب فقط (أرقام فقط). إذا لم يوجد رقم، ضع null.

    صيغة الرد المطلوبة:
    {"is_order": bool, "order_id": string or null}
    """
    
    headers = {"Authorization": f"Bearer {GROK_API_KEY}"}
    payload = {
        "model": "grok-1",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message}
        ],
        "temperature": 0  # نبقيها 0 لضمان استجابة رياضية دقيقة وعدم التأليف
    }
    
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, json=payload, headers=headers)
            content = r.json()["choices"][0]["message"]["content"]
            
            # 💡 تنظيف النص: إزالة علامات الاقتباس الخلفية التي تضيفها نماذج الذكاء الاصطناعي أحياناً
            clean_content = content.replace("```json", "").replace("```", "").strip()
            
            return json.loads(clean_content)
            
        except Exception as e:
            # تسجيل الخطأ لكي تراجعه لاحقاً دون أن يتوقف البوت
            logger.error(f"Grok Intent Parsing Error: {str(e)} - Content: {content if 'content' in locals() else 'None'}")
            
            # إرجاع حالة افتراضية آمنة حتى يكمل البوت المحادثة بشكل طبيعي
            return {"is_order": False, "order_id": None}



async def grok_generate_reply(history: List[Dict], context: str, system_prompt: str) -> str:
    """توليد رد بشري وذكي بناءً على السياق وتاريخ المحادثة"""
    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # تحسين السياق: إذا لم يتوفر سياق (مثل رقم الطلب)، نخبر البوت بذلك لكي لا يؤلف معلومات
    extra_context = context if context else "لا توجد بيانات طلب محددة حالياً. أجب بناءً على معلومات المتجر العامة فقط."
    
    full_system = f"{system_prompt}\n\n[سياق النظام الحالي]:\n{extra_context}"
    
    # التأكد من أن التاريخ لا يتجاوز عدداً معيناً لتوفير التكلفة وسرعة الرد
    compact_history = history[-6:] # آخر 6 رسائل تكفي للحفاظ على سياق المحادثة
    
    messages = [{"role": "system", "content": full_system}] + compact_history

    # --- محاكاة السلوك البشري (Human-like Delay) ---
    # البشر يحتاجون وقتاً للقراءة والكتابة، سننتظر بين 2 إلى 4 ثوانٍ قبل طلب الرد
    await asyncio.sleep(random.uniform(2.0, 4.0))

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url, 
                json={
                    "model": "grok-1", 
                    "messages": messages,
                    "temperature": 0.7, # رفعنا الحرارة قليلاً ليكون الكلام بشرياً وليس آلياً جامداً
                    "max_tokens": 500
                }, 
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code == 200:
                reply = response.json()["choices"][0]["message"]["content"]
                
                # لمسة أخيرة: محاكاة وقت "الكتابة" بناءً على طول الرد
                typing_time = len(reply) * 0.05 # 0.05 ثانية لكل حرف
                await asyncio.sleep(min(typing_time, 3.0)) # لا ننتظر أكثر من 3 ثوانٍ إضافية
                
                return reply
            else:
                logger.error(f"Grok API Error: {response.status_code} - {response.text}")
                return "المعذرة منك، يبدو أن هناك ضغط بسيط على النظام. كيف أقدر أساعدك بشيء آخر؟"
                
        except Exception as e:
            logger.error(f"Error in grok_generate_reply: {str(e)}")
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
    """إرسال رسالة عبر متصفح متجر محدد باستخدام نظام الجلسات الموحد"""
    try:
        # 1. التأكد من جاهزية المتصفح واستعادة الجلسة لهذا المتجر تحديداً
        # نستخدم ensure_browser_ready لضمان أن المتصفح يعمل والـ Session محملة
        page = await ensure_browser_ready(store_id)
        
        if not page:
            logger.error(f"❌ تعذر تجهيز المتصفح للمتجر {store_id}")
            return False

        # 2. فحص ما إذا كان الواتساب يطلب مسح الـ QR (جلسة منتهية)
        qr_canvas = await page.query_selector("canvas")
        if qr_canvas:
            logger.error(f"⚠️ المتجر {store_id} يحتاج لإعادة مسح كود QR (الجلسة غير صالحة)")
            return False

        # 3. تنظيف رقم الهاتف وتجهيز الرابط
        clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")
        url = f"https://web.whatsapp.com/send?phone={clean_phone}&text={text}" 
        # ملاحظة: وضع النص في الرابط أحياناً يكون أسرع وأدق
        
        # 4. الانتقال إلى المحادثة
        logger.info(f"⏳ جاري الدخول لمحادثة {clean_phone}...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # 5. الانتظار حتى يظهر صندوق الكتابة (تأكيد تحميل المحادثة)
        input_selector = 'div[contenteditable="true"][data-tab="10"]'
        try:
            await page.wait_for_selector(input_selector, timeout=35000)
            
            # 6. محاكاة الكتابة البشرية (اختياري لو أردت كتابة النص يدوياً بدل الرابط)
            # await page.keyboard.type(text, delay=random.randint(30, 70))
            
            # 7. الضغط على إرسال (Enter)
            await asyncio.sleep(random.uniform(1, 2)) # وقفة بسيطة للتمويه
            await page.keyboard.press("Enter")
            
            logger.info(f"✅ تم إرسال الرسالة بنجاح للرقم {phone} عبر المتجر {store_id}")
            return True
            
        except Exception as timeout_e:
            logger.error(f"⏳ استغرق تحميل صندوق المحادثة وقتاً طويلاً للرقم {phone}")
            return False

    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في إرسال رسالة المتجر {store_id}: {e}")
        return False

async def get_merchant_stats(store_id: str):
    """جلب إحصائيات المتجر من سلة"""
    res = supabase.table("store_settings").select("salla_access_token").eq("store_id", store_id).single().execute()
    token = res.data["salla_access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        # 1. جلب إحصائيات الطلبات
        orders_resp = await client.get("https://api.salla.dev/admin/v2/reports/orders", headers=headers)
        # 2. جلب السلال المتروكة
        abandoned_resp = await client.get("https://api.salla.dev/admin/v2/abandoned-carts", headers=headers)
        
        return {
            "orders": orders_resp.json().get("data"),
            "abandoned_carts_count": abandoned_resp.json().get("pagination", {}).get("total")
        }
        
async def close_inactive_stores(max_idle_time=3600):
    """إغلاق صفحات المتاجر التي لم ترسل رسائل منذ ساعة لتوفير الرام"""
    # يمكنك إضافة منطق تسجيل وقت آخر نشاط لكل store_id في قاموس
    pass


async def send_admin_alert(store_id: str, customer_phone: str, last_message: str):
    """إرسال تنبيه لمالك المتجر عند طلب تدخل بشري"""
    # جلب رقم جوال التاجر (الآدمن) من قاعدة البيانات
    res = supabase.table("store_settings").select("admin_phone").eq("store_id", store_id).single().execute()
    if not res.data or not res.data.get("admin_phone"): return

    admin_phone = res.data["admin_phone"]
    alert_text = (
        f"🚨 *تنبيه تدخل بشري!*\n\n"
        f"🏪 متجر: {store_id}\n"
        f"👤 العميل: {customer_phone}\n"
        f"💬 آخر رسالة: {last_message}\n\n"
        f"يرجى الدخول للوحة التحكم للرد."
    )
    
    # نستخدم نفس دالة الإرسال لكن للتاجر
    await send_whatsapp_dynamic(store_id, admin_phone, alert_text)

# --- خدمات سلة شات (Salla Chat API) ---

async def send_salla_chat(store_id: str, conversation_id: str, text: str):
    """إرسال رد مباشر إلى محادثة العميل داخل متجر سلة"""
    # جلب التوكن الحالي
    res = supabase.table("store_settings").select("salla_access_token").eq("store_id", store_id).single().execute()
    token = res.data["salla_access_token"]
    
    url = f"https://api.salla.dev/admin/v2/chats/{conversation_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={"message": text}, headers=headers)
        if resp.status_code == 401: # محاولة تجديد التوكن إذا انتهى
            new_token = await refresh_salla_token(store_id)
            if new_token:
                headers["Authorization"] = f"Bearer {new_token}"
                await client.post(url, json={"message": text}, headers=headers)


async def check_abandoned_carts_and_remind(store_id: str):
    """البحث عن السلال المتروكة وإرسال تذكير ذكي للعملاء"""
    # 1. جلب بيانات السلال المتروكة من سلة
    carts_data = await salla_request("GET", "abandoned-carts", store_id)
    if not carts_data or "data" not in carts_data:
        return

    for cart in carts_data["data"]:
        # التحقق مما إذا كان العميل قد تم تذكيره سابقاً (لتجنب الإزعاج)
        cart_id = str(cart["id"])
        is_reminded = supabase.table("reminders_log").select("*").eq("cart_id", cart_id).execute()
        
        if not is_reminded.data:
            customer_phone = cart["customer"]["mobile"]
            customer_name = cart["customer"]["first_name"]
            cart_url = cart["checkout_url"] # رابط العودة للسلة
            
            # إنشاء رسالة تذكير جذابة (يمكن جعلها ذكية عبر Grok)
            reminder_text = (
                f"يا هلا يا {customer_name} 🌹،\n\n"
                f"لاحظنا إنك تركت بعض المنتجات الرائعة في سلتك بمتجرنا. "
                f"حبينا نذكرك إنها لسه بانتظارك وممكن تنفد في أي وقت!\n\n"
                f"بإمكانك إكمال طلبك مباشرة من هنا:\n{cart_url}\n\n"
                f"إذا واجهت أي مشكلة، أنا هنا لمساعدتك."
            )
            
            # وضع الرسالة في الطابور للإرسال عبر المتصفح
            await message_queue.put((customer_phone, reminder_text))
            
            # تسجيل التذكير في قاعدة البيانات لعدم التكرار
            supabase.table("reminders_log").insert({
                "cart_id": cart_id,
                "store_id": store_id,
                "customer_phone": customer_phone,
                "sent_at": datetime.now().isoformat()
            }).execute()
            
            # انتظار بسيط لتجنب الضغط على السيرفر أثناء المعالجة
            await asyncio.sleep(2)


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
    """
    نسخة احترافية من الـ Webhook تدعم المعالجة المتوازية والحماية من الأخطاء
    """
    try:
        data = await request.json()
        
        # 1. فلترة الرسائل (التأكد أنها رسالة نصية وليست "تأكيد استلام" أو "وسائط")
        changes = data.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {})
        if 'messages' not in changes:
            return {"status": "ignored", "reason": "not_a_message"}

        msg_obj = changes['messages'][0]
        phone = msg_obj.get('from')
        text = msg_obj.get('text', {}).get('body', '').strip()
        
        if not text:
            return {"status": "ignored", "reason": "empty_text"}

        # 2. جلب معرف المتجر (في الإنتاج يفضل استخراجه من الـ Meta Business ID)
        store_id = "STORE_001" 

        # 3. تشغيل المعالجة الثقيلة في الخلفية (Background Task)
        # هذا يضمن الرد على سيرفر واتساب فوراً بـ 200 OK لتجنب تكرار إرسال الرسالة إليك
        background_tasks.add_task(process_customer_request, store_id, phone, text)

        return {"status": "request_queued"}

    except Exception as e:
        logger.error(f"Critical Webhook Error: {str(e)}")
        # نرد بـ 200 دائماً لسيرفر واتساب حتى لا يعيد المحاولة ويسبب Loop
        return {"status": "error", "message": "logged"}

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
async def groq_analyze_intent(message: str) -> dict:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}", "Content-Type": "application/json"}
    
    # برومبت دقيق جداً لاستخراج اسم المنتج
    prompt = """
    تحليل رسالة العميل وإرجاع JSON فقط:
    {
      "is_order": bool,      // إذا كان يسأل عن حالة طلب أو تتبع
      "order_id": string,    // رقم الطلب إن وجد
      "is_product": bool,    // إذا كان يستفسر عن منتج معين، سعره، أو توفره
      "product_name": string // اسم المنتج المستخلص من الجملة (مثلاً: "قهوة باجا")
    }
    """
    
    payload = {
        "model": "llama3-70b-8192", # نستخدم الموديل الأكبر للدقة في التحليل
        "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": message}],
        "response_format": {"type": "json_object"}
    }
    
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, json=payload, headers=headers)
            return json.loads(r.json()["choices"][0]["message"]["content"])
        except:
            return {"is_order": False, "order_id": None, "is_product": False, "product_name": None}

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

async def groq_generate_reply(history: list, context: str, system_prompt: str) -> str:
    """توليد رد ذكي وبشري فوري"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"}
    
    full_prompt = f"{system_prompt}\n\nContext: {context}"
    messages = [{"role": "system", "content": full_prompt}] + history

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, json={
                "model": "llama3-8b-8192", # نستخدم 8b هنا لسرعة مذهلة في الردود
                "messages": messages,
                "temperature": 0.7
            }, headers=headers)
            return r.json()["choices"][0]["message"]["content"]
        except:
            return "يا هلا بك، كيف أقدر أساعدك اليوم؟"



@app.post("/webhook/salla")
async def handle_salla_event(request: Request, background_tasks: BackgroundTasks):
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
        supabase.table("store_settings").update({"is_active": True}).eq("store_id", store_id).execute()
    elif event == "app.subscription.expired":
        supabase.table("store_settings").update({"is_active": False}).eq("store_id", store_id).execute()

    # 2. ميزة تتبع الأرباح (عند إنشاء طلب جديد)
    if event == "order.created":
        order_data = data.get("data", {})
        customer_phone = order_data.get("customer", {}).get("mobile")
        order_total = order_data.get("total", {}).get("amount") # قيمة الطلب
        
        # البحث عن آخر تذكير أرسله البوت لهذا الرقم في آخر 24 ساعة
        recent_reminder = supabase.table("reminders_log")\
            .select("id")\
            .eq("customer_phone", customer_phone)\
            .eq("store_id", store_id)\
            .order("sent_at", desc=True)\
            .limit(1).execute()
            
        if recent_reminder.data:
            # 💡 تحديث السجل: هذا الطلب تم بفضل البوت!
            reminder_id = recent_reminder.data[0]["id"]
            supabase.table("reminders_log").update({
                "is_recovered": True,
                "recovered_amount": order_total,
                "recovered_at": datetime.now().isoformat()
            }).eq("id", reminder_id).execute()
            logger.info(f"💰 مبيعات مستردة! الطلب تم بفضل البوت للمتجر {store_id}")

    # 3. ميزة تسليم المنتجات الرقمية (عند تحديث الطلب لـ تم التنفيذ)
    elif event == "order.updated":
        order_data = data.get("data", {})
        status = order_data.get("status", {}).get("id")
        
        if status == 21: # حالة "تم التنفيذ"
            order_id = order_data.get("id")
            customer_phone = order_data.get("customer", {}).get("mobile")
            items = order_data.get("items", [])
            digital_contents = []

            for item in items:
                codes = item.get("codes", [])
                files = item.get("files", [])
                if codes:
                    for code in codes: digital_contents.append(f"🔑 كود {item['name']}: {code['code']}")
                if files:
                    for file in files: digital_contents.append(f"📁 ملف {item['name']}: {file['url']}")

            if digital_contents:
                delivery_msg = f"🎉 *تم تنفيذ طلبك #{order_id}*\n\n" + "\n".join(digital_contents)
                background_tasks.add_task(message_queue.put, (store_id, customer_phone, delivery_msg))

    # 4. معالجة رسائل الشات والذكاء الاصطناعي
    elif event == "chat.message.created":
        msg_data = data.get("data", {})
        if msg_data.get("type") == "sent_by_customer":
            conversation_id = msg_data.get("conversation_id")
            text = msg_data.get("message")
            customer_info = msg_data.get("customer", {})
            phone = customer_info.get("mobile")
            salla_id = str(msg_data.get("customer_id"))

            # توحيد هوية العميل وحفظ الرسالة
            cust = supabase.table("customers").upsert({
                "phone_number": phone, "salla_customer_id": salla_id,
                "name": f"{customer_info.get('first_name', '')} {customer_info.get('last_name', '')}"
            }, on_conflict="phone_number").execute()
            cust_db_id = cust.data[0]['id']
            supabase.table("conversations").insert({"customer_id": cust_db_id, "role": "user", "content": text}).execute()
            
            # تحليل وتوليد رد عبر Grok
            analysis = await grok_analyze_intent(text)
            context = await get_salla_order(analysis["order_id"], store_id) if analysis["order_id"] else ""
            history_res = supabase.table("conversations").select("role, content").eq("customer_id", cust_db_id).order("created_at", desc=True).limit(5).execute()
            history = [{"role": r["role"], "content": r["content"]} for r in reversed(history_res.data)]
            settings = supabase.table("store_settings").select("system_prompt").eq("store_id", store_id).single().execute()
            reply = await grok_generate_reply(history, context, settings.data["system_prompt"])

            # التحقق من التدخل البشري والرد
            if "[HUMAN_REQUIRED]" in reply or "موظف" in text:
                background_tasks.add_task(send_admin_alert, store_id, phone, text)
                human_msg = "تم تحويل طلبك للموظف المختص، سيتواصل معك أحد زملائنا قريباً."
                background_tasks.add_task(send_salla_chat, store_id, conversation_id, human_msg)
                supabase.table("conversations").insert({"customer_id": cust_db_id, "role": "system", "content": "human_transfer_triggered"}).execute()
            else:
                supabase.table("conversations").insert({"customer_id": cust_db_id, "role": "assistant", "content": reply}).execute()
                background_tasks.add_task(send_salla_chat, store_id, conversation_id, reply)

    return {"status": "ok"}



from fastapi.responses import HTMLResponse

@app.get("/admin/{store_id}", response_class=HTMLResponse)
async def admin_panel(store_id: str):
    try:
        # قراءة محتوى الملف المنفصل
        with open("index.html", "r", encoding="utf-8") as f:
            content = f.read()
        
        # استبدال المعرف الثابت بالمعرف الديناميكي لكل تاجر
        # في ملف index.html تأكد أنك تستخدم هذا المعرف في الـ JS
        content = content.replace('const storeId = "STORE_001";', f'const storeId = "{store_id}";')
        
        return HTMLResponse(content=content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>خطأ: ملف index.html غير موجود في السيرفر</h1>", status_code=404)


@app.get("/admin/dashboard/{store_id}")
async def get_dashboard_data(store_id: str):
    """جلب كافة بيانات لوحة التحكم: الأرباح، الرسم البياني، المحادثات، وحالة الاتصال"""
    # ملاحظة: تأكد من تعريف browser_instance في المستوى العام للملف
    global browser_instance
    
    try:
        # 1. تحديد النطاق الزمني (آخر 7 أيام)
        today = datetime.now()
        last_week = today - timedelta(days=7)

        # 2. جلب سجلات الاسترداد الناجحة (الأرباح)
        revenue_res = supabase.table("reminders_log") \
                .select("recovered_amount, recovered_at") \
                .eq("store_id", store_id) \
                .eq("is_recovered", True) \
                .gte("recovered_at", last_week.isoformat()) \
                .execute()
        
        revenue_data = revenue_res.data or []
        total_revenue = sum(float(row['recovered_amount']) for row in revenue_data)

        # 3. معالجة بيانات الرسم البياني
        days_map = {}
        arabic_days = {
                "Saturday": "السبت", "Sunday": "الأحد", "Monday": "الاثنين", 
                "Tuesday": "الثلاثاء", "Wednesday": "الأربعاء", "Thursday": "الخميس", "Friday": "الجمعة"
        }
        
        # ترتيب الأيام لضمان ظهورها بشكل صحيح من الأقدم للأحدث
        for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                days_map[d.strftime('%A')] = 0

        for row in revenue_data:
                # تحويل النص إلى كائن datetime للتأكد من اليوم
                dt_obj = datetime.fromisoformat(row['recovered_at'].replace('Z', '+00:00'))
                d_name = dt_obj.strftime('%A')
                if d_name in days_map:
                        days_map[d_name] += float(row['recovered_amount'])

        chart_labels = [arabic_days[d] for d in days_map.keys()]
        chart_values = list(days_map.values())

        # 4. جلب إحصائيات سلة والردود الآلية
        conv_count = supabase.table("conversations") \
                .select("id", count="exact").eq("role", "assistant").execute()
            
        abandoned_res = supabase.table("reminders_log") \
                .select("id", count="exact").eq("store_id", store_id).execute()

        # جلب أحدث عملية استرداد لإرسال التنبيه (Toast)
        recent_recoveries_res = supabase.table("reminders_log") \
                .select("id, recovered_amount, customer_phone") \
                .eq("store_id", store_id) \
                .eq("is_recovered", True) \
                .order("recovered_at", desc=True) \
                .limit(1) \
                .execute()

        # 5. جلب آخر 10 محادثات
        recent_chats = supabase.table("conversations") \
                .select("*, customers(phone_number)") \
                .order("created_at", desc=True).limit(10).execute()

        # 6. فحص حالة المتصفح (Playwright)
        is_browser_alive = False
        try:
                # تأكد أن المتصفح يعمل ولم يتم إغلاقه بواسطة ريندر بسبب استهلاك الرام
                if 'browser_instance' in globals() and browser_instance and browser_instance.is_connected():
                        is_browser_alive = True
        except:
                is_browser_alive = False

        # 7. الرد النهائي الموحد بإزاحة 8 مسافات
        return {
                "summary": {
                        "total_revenue_saved": total_revenue
                },
                "recent_recoveries": [
                        {"id": r['id'], "amount": float(r['recovered_amount']), "phone": r['customer_phone']} 
                        for r in (recent_recoveries_res.data or [])
                ],
                "bot_usage": conv_count.count if conv_count.count else 0,
                "salla_stats": {
                        "abandoned_carts_count": abandoned_res.count if abandoned_res.count else 0
                },
                "charts_data": {
                        "labels": chart_labels,
                        "values": chart_values
                },
                "recent_activity": recent_chats.data if recent_chats.data else [],
                "browser_connected": is_browser_alive
        }

    except Exception as e:
        logger.error(f"Dashboard Data Error: {str(e)}")
        return {"error": f"حدث خطأ أثناء تحديث البيانات: {str(e)}"}

@app.get("/admin/advanced-stats/{store_id}")
async def get_advanced_analytics(store_id: str):
    try:
        # 1. إجمالي السلال المتروكة التي تمت مراسلتها
        reminded_carts = supabase.table("reminders_log")\
            .select("cart_id", count="exact")\
            .eq("store_id", store_id).execute()
        
        # 2. جلب الطلبات الناجحة التي تمت "بعد" إرسال تذكير (تحويل ناجح)
        # نقوم بمقارنة أرقام الجوال في السلال المتروكة مع الطلبات الجديدة
        successful_recoveries = supabase.table("reminders_log")\
            .select("customer_phone, cart_id")\
            .eq("store_id", store_id)\
            .eq("is_recovered", True).execute() # نحتاج إضافة حقل is_recovered للجدول

        # 3. حساب إجمالي الأرباح المستردة (Sum of Order Totals)
        # نفترض وجود حقل recovered_amount في جدول السجلات
        total_recovered_revenue = supabase.rpc('get_total_recovered', {'store_param': store_id}).execute()

        # 4. أداء الذكاء الاصطناعي (AI vs Human)
        ai_responses = supabase.table("conversations")\
            .select("id", count="exact").eq("role", "assistant").execute()
            
        human_requests = supabase.table("conversations")\
            .select("id", count="exact").eq("content", "human_transfer_triggered").execute()

        return {
            "summary": {
                "total_reminders_sent": reminded_carts.count or 0,
                "recovered_carts_count": len(successful_recoveries.data) or 0,
                "recovery_rate": f"{(len(successful_recoveries.data) / reminded_carts.count * 100) if reminded_carts.count else 0:.1f}%",
                "total_revenue_saved": total_recovered_revenue.data or 0
            },
            "ai_performance": {
                "automated_chats": ai_responses.count or 0,
                "human_intervention_rate": f"{(human_requests.count / ai_responses.count * 100) if ai_responses.count else 0:.1f}%"
            },
            "charts_data": {
                "labels": ["السبت", "الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة"],
                "data": [12, 19, 3, 5, 2, 3, 10] # بيانات تجريبية للرسم البياني
            }
        }
    except Exception as e:
        logger.error(f"Analytics Error: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/admin/update-config/{store_id}")
async def update_config(store_id: str, settings: dict):
    """تحديث إعدادات المسؤول والبرومبت من لوحة التحكم"""
    try:
        supabase.table("store_settings").update({
            "admin_phone": settings.get("admin_phone"),
            "system_prompt": settings.get("system_prompt")
        }).eq("store_id", store_id).execute()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/get-qr/{store_id}")
async def get_whatsapp_qr(store_id: str):
    # نطلب الصفحة الخاصة بهذا التاجر تحديداً
    page = await get_handler_for_store(store_id)
    
    try:
        await page.wait_for_selector("canvas", timeout=15000)
        qr_element = await page.query_selector("canvas")
        img_bytes = await qr_element.screenshot()
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return {"qr_code": f"data:image/png;base64,{img_base64}"}
    except:
        return {"status": "connected", "message": "الجهاز مرتبك بالفعل"}

# دالة إرسال الرسالة الجديدة باستخدام المتصفح المفتوح

@app.get("/callback")
async def salla_callback(code: str, state: str = None):
    """استقبال التاجر بعد تثبيت التطبيق وتخزين بياناته"""
    url = "https://accounts.salla.sa/oauth2/token"
    payload = {
        "client_id": os.getenv("SALLA_CLIENT_ID"),
        "client_secret": os.getenv("SALLA_CLIENT_SECRET"),
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": os.getenv("SALLA_CALLBACK_URL"),
        "scope": "offline_access"
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=payload)
        if resp.status_code == 200:
            data = resp.json()
            # استخراج معرف المتجر من التوكن (عبر Salla User Info API)
            user_info = await client.get("https://accounts.salla.sa/oauth2/user/info", 
                                        headers={"Authorization": f"Bearer {data['access_token']}"})
            store_id = user_info.json()["data"]["merchant"]["id"]
            
            # حفظ التاجر في قاعدة البيانات وتفعيل وضع "التجربة" أو "الاشتراك"
            supabase.table("store_settings").upsert({
                "store_id": str(store_id),
                "salla_access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "is_active": True # تفعيل البوت
            }).execute()
            
            return {"status": "success", "message": "تم ربط المتجر بنجاح! يمكنك الآن العودة للوحة التحكم."}
    
    raise HTTPException(status_code=400, detail="فشل عملية الربط")



@app.get("/")
def health_check():
    return {"status": "active", "time": datetime.now()}
