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
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta
import logging
from fastapi.responses import HTMLResponse
import psycopg2  
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse 

templates = Jinja2Templates(directory=".") 
# إعداد الـ Logger لضمان ظهور الأخطاء في سجلات ريندر
logger = logging.getLogger(__name__)

app = FastAPI()

# إذا كان لديك ملفات CSS أو JS خارجية (اختياري)
# app.mount("/static", StaticFiles(directory="static"), name="static")


# تأكد من وجود المسارات التي يطلبها الـ JavaScript في ملفك


logger = logging.getLogger("jaddahh")
def get_db_connection():
    # تأكد أن DATABASE_URL موجود في إعدادات ريندر ويبدأ بـ postgresql://
    conn = psycopg2.connect(os.environ.get("DATABASE_URL"), sslmode='require')
    return conn


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
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(whatsapp_worker())


# تشغيل العامل عند بدء التطبيق

def verify_salla_signature(payload: bytes, signature: str, secret: str):
    computed_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_sig, signature)

# --- خدمات SALLA (Authentication & Data) ---
# نحتاج لتخزين كائن playwright لإغلاقه بشكل صحيح




# تحديد مسار حفظ بيانات الجلسة (سيتم إنشاء مجلد في نفس مسار السكربت)




async def get_handler_for_store(store_id: str):
    """
    الدالة المركزية والموحدة: جلب أو إنشاء صفحة واتساب مع استعادة الجلسة.
    تم دمج التحسينات الأمنية وإدارة الرام في مكان واحد.
    """
    global playwright_manager, pages, contexts
    
    # 1. التحقق مما إذا كانت الصفحة مفتوحة ونشطة بالفعل
    if store_id in pages and not pages[store_id].is_closed():
        try:
            # فحص سريع للتأكد من أن الصفحة تستجيب (لتفادي الصفحات المعلقة)
            await pages[store_id].evaluate("1+1")
            return pages[store_id]
        except Exception:
            logger.warning(f"🔄 صفحة المتجر {store_id} لا تستجيب، سيتم إعادة تهيئتها...")
            # تنظيف المراجع القديمة الميتة
            if store_id in contexts:
                await contexts[store_id].close()
            pages.pop(store_id, None)
            contexts.pop(store_id, None)

    # 2. التأكد من وجود المجلد الرئيسي للجلسات
    if not os.path.exists(SESSION_PATH):
        os.makedirs(SESSION_PATH, exist_ok=True)

    # 3. تشغيل محرك Playwright الرئيسي (مرة واحدة فقط)
    # ملاحظة: تم إزالة browser_instance لأن Persistent Context لا يحتاجه
    if playwright_manager is None:
        playwright_manager = await async_playwright().start()
        logger.info("🚀 تم تشغيل محرك Playwright بنجاح")

    # 4. إدارة الجلسة (الاستعادة من قاعدة البيانات أو محلياً)
    storage_path = os.path.join(SESSION_PATH, f"session_{store_id}")
    if not os.path.exists(storage_path):
        logger.info(f"📥 محاولة استعادة جلسة المتجر {store_id} من Supabase...")
        success = await load_session_from_db(store_id)
        if not success:
            os.makedirs(storage_path, exist_ok=True)
            logger.info(f"🆕 لا توجد جلسة سابقة، سيتم إنشاء مجلد جديد للمتجر {store_id}")

    # 5. تشغيل المتصفح بنظام الـ Persistent Context
    try:
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
        
        # استخدام الصفحة الافتراضية أو فتح واحدة جديدة
        page = context.pages[0] if context.pages else await context.new_page()

        # 6. تحسين الأداء (تذكر أننا عدلنا دالة block_useless_resources سابقاً لعدم حظر الصور)
        await page.route("**/*", block_useless_resources)

        # 7. التوجه لواتساب ويب (فقط إذا لم يكن المتصفح عليه بالفعل)
        if "web.whatsapp.com" not in page.url:
            await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=90000)
        
        # 8. حقن المراقب (Observer) لاستقبال الرسائل
        await setup_inbound_observer(page, store_id)

        # 9. تخزين المراجع للاستخدام اللاحق (مهم جداً للسرعة)
        pages[store_id] = page
        contexts[store_id] = context
        
        logger.info(f"✅ صفحة المتجر {store_id} جاهزة للاستخدام.")
        return page

    except Exception as e:
        logger.error(f"❌ خطأ أثناء تشغيل متصفح المتجر {store_id}: {e}")
        return None


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


async def save_session_to_db(store_id: str):
    try:
        path = os.path.join(SESSION_PATH, f"session_{store_id}")
        if not os.path.exists(path): return

        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            tar.add(path, arcname=os.path.basename(path))
        
        b64_session = base64.b64encode(buffer.getvalue()).decode()
        
        # استخدام UPSERT في PostgreSQL (ON CONFLICT)
        query = """
            INSERT INTO store_sessions (store_id, session_data, updated_at)
            VALUES (:sid, :data, NOW())
            ON CONFLICT (store_id) 
            DO UPDATE SET session_data = EXCLUDED.session_data, updated_at = NOW()
        """
        execute_db_query(query, {"sid": store_id, "data": b64_session})
        logger.info(f"✅ تم حفظ جلسة المتجر {store_id} عبر PostgreSQL.")
    except Exception as e:
        logger.error(f"❌ خطأ أثناء حفظ الجلسة: {e}")

async def load_session_from_db(store_id: str):
    """تحميل الجلسة من PostgreSQL وفك ضغطها محلياً"""
    try:
        # 1. استعلام SQL لجلب البيانات المشفرة (Base64)
        query = "SELECT session_data FROM store_sessions WHERE store_id = :sid LIMIT 1"
        row = execute_db_query(query, {"sid": store_id}, fetch="one")

        # 2. التحقق من وجود بيانات
        if not row or not row[0]:
            logger.warning(f"⚠️ لا توجد جلسة محفوظة في القاعدة للمتجر {store_id}")
            return False

        # 3. معالجة البيانات (Base64 -> Binary -> Extraction)
        b64_data = row[0]
        compressed_data = base64.b64decode(b64_data)
        
        # 4. فك الضغط في المسار المخصص (SESSION_PATH)
        buffer = io.BytesIO(compressed_data)
        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            tar.extractall(path=SESSION_PATH)
        
        logger.info(f"📂 تم استعادة جلسة المتجر {store_id} بنجاح من PostgreSQL.")
        return True

    except Exception as e:
        logger.error(f"❌ خطأ كارثي أثناء تحميل الجلسة للمتجر {store_id}: {e}")
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
    # إزالة "image" من الحظر لكي يظهر الـ QR وتظهر صور المنتجات لاحقاً
    useless_types = ["media", "font", "manifest"] 
    
    if route.request.resource_type in useless_types:
        await route.abort()
    else:
        url = route.request.url
        # لا تقم بحظر أي شيء يخص whatsapp
        if "google-analytics" in url or "facebook" in url:
            await route.abort()
        else:
            await route.continue_()

# الاستخدام داخل الكود
# await page.route("**/*", block_useless_resources)

# داخل دالة فتح الصفحة


async def salla_request(method: str, endpoint: str, store_id: str, payload: dict = None):
    """دالة موحدة لطلبات سلة تعتمد على PostgreSQL مع تجديد تلقائي للتوكن"""
    try:
        # 1. جلب التوكن من قاعدة البيانات مباشرة
        query = "SELECT salla_access_token FROM store_settings WHERE store_id = :sid LIMIT 1"
        row = execute_db_query(query, {"sid": store_id}, fetch="one")
        
        if not row:
            logger.error(f"❌ فشل جلب التوكن للمتجر {store_id}: المتجر غير مسجل.")
            return None
            
        token = row[0]
        url = f"https://api.salla.dev/admin/v2/{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}", 
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            # 2. تنفيذ الطلب بناءً على الطريقة (GET, POST, etc.)
            if method.upper() == "GET":
                resp = await client.get(url, headers=headers)
            else:
                resp = await client.post(url, headers=headers, json=payload)
                
            # 3. معالجة انتهاء صلاحية التوكن (401)
            if resp.status_code == 401:
                logger.warning(f"🔄 توكن المتجر {store_id} منتهي، جاري التجديد...")
                new_token = await refresh_salla_token(store_id)
                
                if new_token:
                    # إعادة المحاولة مرة واحدة فقط بالتوكن الجديد
                    headers["Authorization"] = f"Bearer {new_token}"
                    if method.upper() == "GET":
                        resp = await client.get(url, headers=headers)
                    else:
                        resp = await client.post(url, headers=headers, json=payload)
                else:
                    logger.error(f"❌ فشل تجديد التوكن للمتجر {store_id}")
                    return None

            # 4. إعادة البيانات إذا كان الطلب ناجحاً
            if resp.status_code in [200, 201]:
                return resp.json()
            else:
                logger.error(f"⚠️ Salla API Error [{resp.status_code}]: {resp.text}")
                return None

    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع في salla_request: {str(e)}")
        return None
async def refresh_salla_token(store_id: str) -> Optional[str]:
    # جلب الـ refresh_token فقط من القاعدة
    query = "SELECT refresh_token FROM store_settings WHERE store_id = :sid"
    row = execute_db_query(query, {"sid": store_id}, fetch="one")
    
    if not row: return None
    
    url = "https://accounts.salla.sa/oauth2/token"
    payload = {
        "client_id": os.getenv("SALLA_CLIENT_ID"),         # مفتاح تطبيقك
        "client_secret": os.getenv("SALLA_CLIENT_SECRET"), # سر تطبيقك
        "grant_type": "refresh_token",
        "refresh_token": row[0]
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=payload)
        if resp.status_code == 200:
            data = resp.json()
            # تحديث البيانات عبر SQL
            update_query = """
                UPDATE store_settings 
                SET salla_access_token = :access, refresh_token = :refresh, updated_at = NOW() 
                WHERE store_id = :sid
            """
            execute_db_query(update_query, {
                "access": data["access_token"],
                "refresh": data["refresh_token"],
                "sid": store_id
            })
            return data["access_token"]
        else:
            logger.error(f"❌ فشل تجديد التوكن: {resp.text}")
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

            # تحليل الرد عبر Grok
            analysis = await grok_analyze_intent(text)
            context = await get_salla_order(analysis["order_id"], store_id) if analysis["order_id"] else ""
            reply = await grok_generate_reply(history, context, settings[0] if settings else "You are a helpful assistant")

            # التدخل البشري والرد
            if "[HUMAN_REQUIRED]" in reply or "موظف" in text:
                background_tasks.add_task(send_admin_alert, store_id, phone, text)
                reply = "تم تحويل طلبك للموظف المختص، سيتواصل معك قريباً."
            
            # تسجيل رد البوت وإرساله
            execute_db_query("INSERT INTO conversations (customer_id, role, content) VALUES (:cid, 'assistant', :txt)", 
                             {"cid": cust_db_id, "txt": reply})
            background_tasks.add_task(send_salla_chat, store_id, msg_data.get("conversation_id"), reply)

    return {"status": "ok"}



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


@app.get("/admin/get-qr/{store_id}")
async def get_whatsapp_qr(store_id: str):
    try:
        # 1. التحقق من المتجر
        query = "SELECT is_active FROM store_settings WHERE store_id = :sid LIMIT 1"
        row = execute_db_query(query, {"sid": store_id}, fetch="one")
        if not row: return {"status": "error", "message": "المتجر غير مسجل"}

        # 2. الحصول على الصفحة
        page = await get_handler_for_store(store_id)
        if not page: return {"status": "error", "message": "فشل فتح المتصفح"}

        # تحديث الصفحة لضمان توليد كود جديد
        await page.reload()
        
        try:
            # الانتظار حتى يظهر الـ QR (سواء كان canvas أو img)
            await page.wait_for_selector("canvas, img[alt='Scan me!']", timeout=15000)
            
            # محاولة التقاط الـ QR من الـ canvas أولاً ثم الصور
            qr_element = await page.query_selector("canvas") or await page.query_selector("img[alt='Scan me!']")
            
            if qr_element:
                img_bytes = await qr_element.screenshot()
                img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                return {
                    "status": "ready",
                    "qr_code": f"data:image/png;base64,{img_base64}",
                    "message": "قم بمسح الكود الآن"
                }
        except Exception:
            # فحص إذا كان المستخدم مسجل دخول بالفعل
            if await page.query_selector("div[data-testid='chat-list']"):
                return {"status": "connected", "message": "واتساب متصل بالفعل ✅"}
            return {"status": "error", "message": "انتهت مهلة توليد الكود، حاول مجدداً"}

    except Exception as e:
        logger.error(f"❌ QR Error: {e}")
        return {"status": "error", "message": str(e)}

async def send_whatsapp_message(store_id: str, phone: str, message: str):
    """إرسال رسالة واتساب باستخدام المتصفح المفتوح للمتجر"""
    try:
        page = await get_handler_for_store(store_id)
        if not page:
            logger.error("❌ المتصفح غير جاهز للإرسال")
            return False

        # تنظيف رقم الهاتف (إضافة مفتاح الدولة إذا نقص)
        clean_phone = phone.replace("+", "").replace(" ", "")
        url = f"https://web.whatsapp.com/send?phone={clean_phone}&text={urllib.parse.quote(message)}"
        
        await page.goto(url)
        
        # الانتظار حتى يظهر زر الإرسال (أيقونة الإرسال في واتساب ويب)
        send_button_selector = "span[data-testid='send'], button[data-testid='compose-btn-send']"
        await page.wait_for_selector(send_button_selector, timeout=20000)
        
        # الضغط على زر الإرسال
        await page.click(send_button_selector)
        
        # انتظار بسيط للتأكد من خروج الرسالة قبل إغلاق أو تحويل الصفحة
        await asyncio.sleep(2)
        logger.info(f"✅ تم إرسال الرسالة بنجاح إلى {phone}")
        return True

    except Exception as e:
        logger.error(f"❌ فشل إرسال الرسالة إلى {phone}: {e}")
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
    
@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# 2. هذا المسار سيبقى لفحص الحالة (يمكنك الوصول إليه عبر /health)
@app.get("/health")
def health_check():
    return {
        "status": "online", 
        "engine": "PostgreSQL (Internal)",
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
