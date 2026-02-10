import asyncio
import threading
import sys
import os
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
import pytz
from datetime import datetime
from pyrogram import Client, filters, enums

# --- إعداد السجلات ---
logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)

# --- استيراد الإعدادات ---
try:
    from config import normalize_text, CITIES_DISTRICTS, BOT_TOKEN
    print("✅ تم تحميل الإعدادات بنجاح")
except Exception as e:
    print(f"❌ خطأ في تحميل ملف config.py: {e}")
    sys.exit(1)

# --- متغيرات البيئة ---
API_ID = os.environ.get("API_ID", "33888256")
API_HASH = os.environ.get("API_HASH", "bb1902689a7e203a7aedadb806c08854")
SESSION_STRING = os.environ.get("SESSION_STRING", "BAIFGAAAWH0qADVIqGjuDmtifoW-SQxSznz5ZhQjTbbPT2_wrX7IXCv95zqwku9kG4rpIf_xv3IDkt7CFUETnMEtUIff39Po9PwGgsiivLE1Mrbs6Ymw-h7qQap0oxSpSuIVRzWQT8_DWRJ8NGcTtp8VOJrZ7tjvjDMuVouYYd5ZmGNKry7QCQSRZuNCxc29IUC_eirR4KJKwC5IV1Ve5_Jq3PYYr8nsmiEvYauzrwftmivipkmg9CDyQfVxBfJmKi9WJuWQVvTqJWeIYYkBFLJmkcjOAKsej9fqzD4laRJIsKXaVxgfwmX5STeBpjBI7EPlMn9v0UvKQT49rYNQer0UyRSUWAAAAAH9nH9OAA")

CHANNEL_ID = -1003843717541 
TARGET_USERS = [7996171713, 7513630480, 669659550, 6813059801, 632620058, 7093887960]

# --- عملاء تليجرام ---
user_app = Client("my_session", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH)
bot_sender = Bot(token=BOT_TOKEN)

# --- قوائم الفلترة (كما هي في كودك) ---
BLOCK_KEYWORDS = [
    "متواجد", "متاح", "شغال", "جاهز", "أسعارنا", "سيارة نظيفة", "نقل عفش", 
    "دربك سمح", "توصيل مشاوير", "أوصل", "اوصل", "اتصال", "واتساب", "للتواصل",
    "خاص", "الخاص", "بخدمتكم", "خدمتكم", "أستقبل", "استقبل", "نقل بضائع",
    "مشاويركم", "سياره نظيفه", "فان", "دباب", "سطحه", "سطحة", "كابتن", 
    "مندوب", "مناديب", "توصيل طلبات", "ارخص الأسعار", "أرخص الأسعار", "بأسعار",
    "عقار", "عقارات", "للبيع", "للإيجار", "للايجار", "دور", "شقة", "شقه",
    "رخصة فال", "رخصة", "رخصه", "مخطط", "أرض", "ارض", "فلة", "فله", 
    "عماره", "عمارة", "استثمار", "صك", "إفراغ", "الوساطة العقارية", "تجاري", "سكني",
    "اشتراك", "باقات", "تسجيل", "تأمين", "تفويض", "تجديد", "قرض", "تمويل", 
    "بنك", "تسديد", "مخالفات", "اعلان", "إعلان", "قروب", "مجموعة", "انضم", 
    "رابط", "نشر", "قوانين", "احترام", "الذوق العام", "استقدام", "خادمات",
    "تعقيب", "معقب", "انجاز", "إنجاز", "كفيل", "نقل كفالة", "اسقاط", "تعديل مهنة",
    "حياك الله", "نورتنا", "انضمامك", "أهلاً بك", "اهلا بك", "قواعد المجموعة",
    "مرحباً بك", "مرحبا بك", "تنبيه", "محظور", "يُمنع", "يمنع", "بالتوفيق للجميع",
    "http", "t.me", ".com", "رابط القناة", "اخلاء مسؤولية", "ذمة",
    # الكلمات الجديدة المضافة:
    "استثمار", "زواج", "مسيار", "خطابه", "خطابة"
]

# قائمة 2: كلمات خارج السياق (طبي، أعذار، استفسارات عامة) - حظر فوري
IRRELEVANT_TOPICS = [
    "عيادة", "عياده", "اسنان", "أسنان", "دكتور", "طبيب", "مستشفى", "مستوصف",
    "علاج", "تركيب", "تقويم", "خلع", "حشو", "تنظيف", "استفسار", "افضل", "أفضل",
    "تجربة", "مين جرب", "رأيكم", "تنصحون", "ورشة", "سمكري", "قطع غيار",
    # الكلمات الجديدة المضافة:
    "عذر طبي", "سكليف", "سكليفات"
]

def analyze_message_by_districts(text):
    if not text: return None
    
    # --- شرط طول الرسالة ---
    # إذا كانت الرسالة أطول من 200 حرف، غالباً ما تكون إعلان أو قوانين مجموعة
    if len(text) > 200 or len(text) < 5: 
        return None

    clean_text = normalize_text(text)
    
    # فحص الكلمات المحظورة (موجودة مسبقاً في كودك)
    if any(k in clean_text for k in BLOCK_KEYWORDS): return None
    if any(k in clean_text for k in IRRELEVANT_TOPICS): return None

    # البحث عن المنطقة (الحي)
    detected_district = None
    for city, districts in CITIES_DISTRICTS.items():
        for d in districts:
            if normalize_text(d) in clean_text:
                detected_district = d
                break
        if detected_district: break

    if not detected_district: return None

    # --- الكلمات المفتاحية الجديدة المطلوبة ---
    order_indicators = [
    # كلماتك الأصلية
    "ابي", "ابغي", "مين", "مشوار", "من", "سائق", 
    "توصيل", "شهري", "ابغى", "دوام", "يوديني",
    
    # كلمات إضافية مقترحة
    "سواق", "توصيلة", "يوصل", "مشاوير", "جامعه", 
    "مدرسه", "موعد", "مستشفى", "يومي", "عقد", "يعرف", "أحد", "وديني", "تروح"
]

    
    # التحقق من وجود أحد الكلمات المطلوبة في النص
    if any(word in clean_text for word in order_indicators):
        return detected_district
        
    return None

async def notify_all(detected_district, msg):
    content = msg.text or msg.caption
    customer = msg.from_user
    bot_username = "Mishweribot"

    # رابط المراسلة
    gate_contact = f"https://t.me/{bot_username}?start=contact_{customer.id if customer else 0}"
    
    # 1. إرسال للقناة (عام)
    chan_text = f"🎯 <b>طلب مشوار جديد</b>\n\n📍 <b>المنطقة:</b> {detected_district}\n📝 <b>التفاصيل:</b>\n<i>{content}</i>"
    try:
        await bot_sender.send_message(
            chat_id=CHANNEL_ID, 
            text=chan_text, 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 مراسلة العميل", url=gate_contact)]]), 
            parse_mode=ParseMode.HTML
        )
    except: pass

    # 2. جلب السائقين المشتركين حالياً من قاعدة البيانات
    active_drivers = await get_active_drivers()
    
    user_text = f"🎯 <b>طلب جديد (للمشتركين فقط)!</b>\n\n📍 <b>المنطقة:</b> {detected_district}\n👤 <b>العميل:</b> {customer.first_name if customer else 'مخفي'}\n📝 <b>النص:</b>\n<i>{content}</i>"

    # 3. الإرسال لكل سائق اشتراكه سارٍ
    for driver_id in active_drivers:
        try:
            await bot_sender.send_message(
                chat_id=driver_id, 
                text=user_text, 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 مراسلة العميل", url=gate_contact)]]), 
                parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(0.1) # تأخير بسيط لتجنب حظر التليجرام
        except:
            continue


async def get_active_drivers():
    conn = get_db_connection()
    if not conn: return []
    
    active_drivers = []
    try:
        def query():
            ksa_tz = pytz.timezone('Asia/Riyadh')
            now_ksa = datetime.now(ksa_tz)
            
            with conn.cursor() as cur:
                # جلب السائقين الذين لديهم تاريخ انتهاء مستقبلي
                cur.execute("""
                    SELECT user_id, subscription_expiry 
                    FROM users 
                    WHERE role = 'driver' 
                    AND subscription_expiry IS NOT NULL
                """)
                rows = cur.fetchall()
                
                drivers = []
                for row in rows:
                    u_id, expiry = row
                    # التأكد من أن الاشتراك لم ينتهِ
                    if expiry and expiry > now_ksa:
                        drivers.append(u_id)
                return drivers

        active_drivers = await asyncio.to_thread(query)
    except Exception as e:
        print(f"❌ Error fetching active drivers: {e}")
    finally:
        release_db_connection(conn)
    return active_drivers

@user_app.on_message(filters.group)
async def handle_new_message(client, message):
    text = message.text or message.caption
    if not text or (message.from_user and message.from_user.is_self): return
    found_district = analyze_message_by_districts(text)
    if found_district:
        await notify_all(found_district, message)

# --- إصلاح مشكلة Peer ID Invalid ---
async def initialize_peers():
    """التعرف التلقائي على جميع القنوات والمجموعات المشترك بها الحساب"""
    print("⏳ جاري فحص وتهيئة جميع المحادثات في الحساب...")
    count = 0
    try:
        # المزامنة مع كافة الحوارات (القنوات، المجموعات، الخاص)
        async for dialog in user_app.get_dialogs():
            # نحن نهتم فقط بالمجموعات والقنوات لعمل الرادار
            if dialog.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL]:
                try:
                    # مجرد الوصول لخصائص الشات يجعل Pyrogram يحفظ المعرف
                    chat_id = dialog.chat.id
                    chat_title = dialog.chat.title
                    count += 1
                    # طباعة دورية كل 5 قنوات لعدم ملء السجلات
                    if count % 5 == 0:
                        print(f"🔄 تمت تهيئة {count} محادثات حتى الآن...")
                except Exception:
                    continue
        
        print(f"✅ تم بنجاح تهيئة {count} قناة ومجموعة. الرادار جاهز الآن!")
    except Exception as e:
        print(f"⚠️ خطأ أثناء محاولة جلب الحوارات: {e}")

# --- خادم الويب ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"Bot Active")
    def log_message(self, format, *args): return

def run_health_server():
    server = HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), HealthCheckHandler)
    server.serve_forever()

# --- التشغيل النهائي المصلح ---
async def main():
    # تشغيل خادم الويب (Render Health Check)
    threading.Thread(target=run_health_server, daemon=True).start()
    
    # بدء تشغيل اليوزر بوت
    await user_app.start()
    
    # خطوة الإصلاح: تهيئة المعرفات قبل بدء استقبال الرسائل
    await initialize_peers()
    
    print("🚀 الرادار يعمل الآن... سيتم تجاهل أخطاء المعرفات القديمة.")
    
    # إبقاء التطبيق يعمل
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
