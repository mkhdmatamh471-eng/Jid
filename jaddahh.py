Import os
import hmac
import hashlib
import json
import logging
import asyncio
import random
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

logger = logging.getLogger(__name__)
browser_instance = None
# قواميس لتخزين الجلسات والصفحات لكل متجر على حدة
contexts: Dict[str, any] = {} 
pages: Dict[str, any] = {}

# 1. الإعدادات والتحميل
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Salla AI Integrated Bot")

SESSION_PATH = os.path.join(os.getcwd(), "whatsapp_session")

# تكوين البيئة
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GROK_API_KEY = os.getenv("GROK_API_KEY")
SALLA_CLIENT_ID = os.getenv("SALLA_CLIENT_ID")
SALLA_CLIENT_SECRET = os.getenv("SALLA_CLIENT_SECRET")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
    """جلب أو إنشاء صفحة واتساب خاصة بمتجر معين (موفر للرام)"""
    global browser_instance, pages, contexts
    
    # 1. تشغيل المحرك الرئيسي (مرة واحدة فقط)
    if not browser_instance or not browser_instance.is_connected():
        playwright = await async_playwright().start()
        browser_instance = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )

    # 2. إذا كانت الصفحة مفتوحة مسبقاً لهذا المتجر، نرجعها
    if store_id in pages and not pages[store_id].is_closed():
        try:
            await pages[store_id].evaluate("1+1")
            return pages[store_id]
        except:
            logger.warning(f"صفحة المتجر {store_id} متوقفة، يتم إعادة التشغيل...")

    # 3. إنشاء سياق (Context) معزول لكل متجر (يحفظ الكوكيز في مجلد خاص)
    storage_path = os.path.join(SESSION_PATH, f"session_{store_id}")
    
    context = await browser_instance.new_context(
        user_data_dir=storage_path,
        viewport={'width': 800, 'height': 600}, # توفير رام
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."
    )
    
    page = await context.new_page()

    # 4. تحسين الرام: منع الصور والوسائط
        # ... (الأكواد السابقة لإنشاء الـ context والـ page) ...

    # 4. تحسين الرام: منع الصور والوسائط (خطوة ذكية جداً)
    await page.route("**/*", lambda route: 
        route.abort() if route.request.resource_type in ["image", "media", "font"] 
        else route.continue_()
    )

    # 5. التوجه إلى واتساب ويب بانتظار تحميل الواجهة الأساسية
    await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=90000)
    
    # 💡 6. حقن "المراقب" فوراً لضمان سماع الرسائل الواردة لهذا المتجر
    # نمرر الـ page ومعرف المتجر store_id
    await setup_inbound_observer(page, store_id)

    pages[store_id] = page
    contexts[store_id] = context
    
    logger.info(f"✅ تم تجهيز صفحة المتجر {store_id} وحقن مراقب الرسائل.")
    return page


# دالة منفصلة لمعالجة المنطق لتجنب التعقيد داخل ensure_browser_ready
async def on_new_message_logic(payload):
    logger.info(f"📩 إشعار: {payload}")
    # أضف هنا كود الضغط على المحادثة واستخراج النص الذي كتبته سابقاً


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
    """جلب بيانات الطلب وتحديث التوكن تلقائياً عند الحاجة"""
    try:
        # 1. جلب التوكن من قاعدة البيانات
        res = supabase.table("store_settings").select("salla_access_token").eq("store_id", store_id).single().execute()
        if not res.data:
            logger.error(f"Store settings not found for: {store_id}")
            return None
            
        token = res.data["salla_access_token"]
        url = f"https://api.salla.dev/admin/v2/orders/{order_id}"
        headers = {"Authorization": f"Bearer {token}"}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            
            # 2. التعامل مع التوكن المنتهي (401)
            if resp.status_code == 401:
                logger.info(f"Token expired for store {store_id}, refreshing...")
                token = await refresh_salla_token(store_id)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    resp = await client.get(url, headers=headers)
            
            # 3. معالجة البيانات المستلمة
            if resp.status_code == 200:
                d = resp.json().get("data", {})
                ref_id = d.get('reference_id')
                status_name = d.get('status', {}).get('name', 'غير معروف')
                total_amount = d.get('total', {}).get('amount', 0)
                currency = d.get('total', {}).get('currency', 'ر.س')
                
                # يمكنك هنا إضافة كود لتحديث جدول reminders_log إذا اكتمل الطلب
                if d.get('status', {}).get('id') == 'completed': # أو المعرف الخاص بالمدفوع
                     update_recovered_status(order_id, total_amount)

                return f"الطلب #{ref_id}: الحالة {status_name}، المجموع: {total_amount} {currency}"
            
            logger.warning(f"Salla API returned status {resp.status_code} for order {order_id}")
            return None

    except Exception as e:
        logger.error(f"Error fetching order {order_id}: {str(e)}")
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
    """إرسال رسالة عبر متصفح متجر محدد"""
    try:
        page = await get_handler_for_store(store_id)
        
        # فحص QR
        qr_canvas = await page.query_selector("canvas")
        if qr_canvas:
            logger.error(f"المتجر {store_id} يحتاج مسح QR")
            return False

        clean_phone = phone.replace("+", "").replace(" ", "")
        url = f"https://web.whatsapp.com/send?phone={clean_phone}"
        
        # التنقل للمحادثة
        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        input_selector = 'div[contenteditable="true"]'
        await page.wait_for_selector(input_selector, timeout=30000)
        
        # الكتابة والارسال
        await page.keyboard.type(text, delay=random.randint(30, 70))
        await asyncio.sleep(1)
        await page.keyboard.press("Enter")
        
        logger.info(f"✅ أرسل المتجر {store_id} رسالة إلى {phone}")
        return True
    except Exception as e:
        logger.error(f"خطأ في إرسال المتجر {store_id}: {e}")
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
        # جلب جميع المتاجر النشطة
        active_stores = supabase.table("store_settings").select("store_id").eq("is_active", True).execute()
        
        for store in active_stores.data:
            try:
                await check_abandoned_carts_and_remind(store["store_id"])
            except Exception as e:
                logger.error(f"Error in cron for store {store['store_id']}: {e}")
        
        # الانتظار لمدة ساعة (3600 ثانية) قبل الفحص القادم
        await asyncio.sleep(3600)

# تحديث دالة بدء التطبيق لتشغيل المجدل
@app.on_event("startup")
async def startup_event():
    # تشغيل عامل إرسال الرسائل
    asyncio.create_task(message_worker())
    
    # تشغيل مجدل السلال المتروكة
    asyncio.create_task(cron_scheduler())
    
    # تهيئة المتصفح فوراً ليكون جاهزاً لاستقبال/إرسال الرسائل
    asyncio.create_task(ensure_browser_ready())
    
    logger.info("🚀 تم تشغيل جميع الخدمات الخلفية بنجاح")

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

async def process_customer_request(store_id: str, phone: str, text: str):
    """المعالج الرئيسي الذي يحتوي على منطق الذكاء الاصطناعي"""
    try:
        # 1. التحقق من الاشتراك والحالة (Cache-friendly)
        store_res = supabase.table("store_settings").select("is_active, system_prompt").eq("store_id", store_id).single().execute()
        if not store_res.data or not store_res.data.get("is_active"):
            return

        # 2. إدارة هوية العميل وحفظ الرسالة الواردة
        cust = supabase.table("customers").upsert({"phone_number": phone}, on_conflict="phone_number").execute()
        cust_id = cust.data[0]['id']
        supabase.table("conversations").insert({"customer_id": cust_id, "role": "user", "content": text}).execute()

        # 3. التحليل وجلب بيانات الطلب (Grok Intent)
        analysis = await grok_analyze_intent(text)
        order_context = ""
        if analysis.get("is_order") and analysis.get("order_id"):
            order_context = await get_salla_order(analysis["order_id"], store_id)

        # 4. جلب تاريخ المحادثة (آخر 5 رسائل)
        history_res = supabase.table("conversations").select("role, content").eq("customer_id", cust_id).order("created_at", desc=True).limit(5).execute()
        history = [{"role": r["role"], "content": r["content"]} for r in reversed(history_res.data)]

        # 5. توليد الرد البشري (Grok Persona)
        reply = await grok_generate_reply(history, order_context, store_res.data["system_prompt"])

        # 6. منطق التدخل البشري
        if "[HUMAN_REQUIRED]" in reply or any(word in text for word in ["موظف", "بشري", "حولني"]):
            human_msg = "أبشر، بحولك الآن لزميلي الموظف يكمل معك. لحظات ويكون معك."
            await message_queue.put((phone, human_msg))
            await send_admin_alert(store_id, phone, text) # تنبيه التاجر
            
            supabase.table("conversations").insert({
                "customer_id": cust_id, 
                "role": "system", 
                "content": "human_transfer_triggered"
            }).execute()
            return

        # 7. حفظ رد البوت وإرساله للعميل
        supabase.table("conversations").insert({"customer_id": cust_id, "role": "assistant", "content": reply}).execute()
        await message_queue.put((store_id, phone, reply))

    except Exception as e:
        logger.error(f"Error processing AI response for {phone}: {str(e)}")

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



@app.get("/admin/dashboard/{store_id}")
async def get_dashboard_data(store_id: str):
    """جلب كافة بيانات لوحة التحكم: الأرباح، الرسم البياني، المحادثات، وحالة الاتصال"""
    global browser_instance
    
    try:
        # 1. تحديد النطاق الزمني (آخر 7 أيام) للرسم البياني والأرباح
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
        total_revenue = sum(row['recovered_amount'] for row in revenue_data)

        # 3. معالجة بيانات الرسم البياني (تجميع المبالغ حسب اليوم)
        days_map = {}
        arabic_days = {
            "Saturday": "السبت", "Sunday": "الأحد", "Monday": "الاثنين", 
            "Tuesday": "الثلاثاء", "Wednesday": "الأربعاء", "Thursday": "الخميس", "Friday": "الجمعة"
        }
        
        # تهيئة آخر 7 أيام بقيمة 0
        for i in range(7):
            d = today - timedelta(days=i)
            days_map[d.strftime('%A')] = 0

        # تعبئة المبالغ المستردة الحقيقية
        for row in revenue_data:
            d_name = datetime.fromisoformat(row['recovered_at']).strftime('%A')
            if d_name in days_map:
                days_map[d_name] += row['recovered_amount']

        chart_labels = [arabic_days[d] for d in reversed(list(days_map.keys()))]
        chart_values = [v for v in reversed(list(days_map.values()))]

        # 4. جلب إحصائيات سلة والردود الآلية
        # إجمالي ردود البوت
        conv_count = supabase.table("conversations") \
            .select("id", count="exact") \
            .eq("role", "assistant") \
            .execute()
            
        # إجمالي السلال المتروكة التي تم رصدها
        abandoned_res = supabase.table("reminders_log") \
            .select("id", count="exact") \
            .eq("store_id", store_id) \
            .execute()

        # 5. جلب آخر 10 محادثات مع بيانات العميل (رقم الهاتف)
        recent_chats = supabase.table("conversations") \
            .select("*, customers(phone_number)") \
            .order("created_at", desc=True) \
            .limit(10) \
            .execute()

        # 6. فحص حالة اتصال المتصفح (Playwright)
        is_browser_alive = False
        try:
            if browser_instance and browser_instance.is_connected():
                is_browser_alive = True
        except:
            is_browser_alive = False

        # 7. تجميع الرد النهائي المتوافق مع واجهة الـ JavaScript لديك
        return {
            "summary": {
                "total_revenue_saved": total_revenue
            },
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
        # إرجاع هيكل بيانات فارغ لتجنب كسر واجهة المستخدم (Frontend)
        return {
            "summary": {"total_revenue_saved": 0},
            "bot_usage": 0,
            "salla_stats": {"abandoned_carts_count": 0},
            "charts_data": {"labels": [], "values": []},
            "recent_activity": [],
            "browser_connected": False,
            "error": "حدث خطأ أثناء تحديث البيانات"
        }

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

@app.post("/admin/settings/{store_id}")
async def update_merchant_settings(store_id: str, wa_phone_id: str, wa_token: str):
    """تحديث إعدادات واتساب التاجر الخاصة"""
    supabase.table("store_settings").update({
        "wa_phone_number_id": wa_phone_id,
        "wa_access_token": wa_token
    }).eq("store_id", store_id).execute()
    return {"status": "updated"}


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
