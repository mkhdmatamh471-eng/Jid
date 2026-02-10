import asyncio
import threading
import sys
import os
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from pyrogram import Client, filters
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

# --- إعداد السجلات ---
logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR) # تقليل سجلات pyrogram لمنع الزحام

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

# --- قوائم الفلترة --- (بقيت كما هي في كودك)
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
    if not text or len(text) < 5: return None
    clean_text = normalize_text(text)
    if any(k in clean_text for k in BLOCK_KEYWORDS): return None
    if any(k in clean_text for k in IRRELEVANT_TOPICS): return None

    detected_district = None
    for city, districts in CITIES_DISTRICTS.items():
        for d in districts:
            if normalize_text(d) in clean_text:
                detected_district = d
                break
        if detected_district: break
    
    if not detected_district: return None
    
    order_indicators = ["ابي", "ابغي", "محتاج", "مطلوب", "توصيل", "مشوار", "بكم", "من", "إلى"]
    if any(word in clean_text for word in order_indicators):
        return detected_district
    return None

# --- وظائف الإرسال ---
async def notify_all(detected_district, msg):
    content = msg.text or msg.caption
    customer = msg.from_user
    bot_username = "Mishweribot"
    
    # رسالة القناة
    gate_contact = f"https://t.me/{bot_username}?start=contact_{customer.id if customer else 0}"
    chan_buttons = [[InlineKeyboardButton("💬 مراسلة العميل", url=gate_contact)]]
    chan_text = f"🎯 <b>طلب مشوار جديد</b>\n\n📍 <b>المنطقة:</b> {detected_district}\n📝 <b>التفاصيل:</b>\n<i>{content}</i>"
    
    # رسالة المستخدمين المستهدفين
    user_buttons = [[InlineKeyboardButton("💬 مراسلة العميل", url=gate_contact)]]
    user_text = f"🎯 <b>طلب جديد!</b>\n\n📍 <b>المنطقة:</b> {detected_district}\n👤 <b>العميل:</b> {customer.first_name if customer else 'مخفي'}\n📝 <b>النص:</b>\n<i>{content}</i>"

    # إرسال للقناة
    try:
        await bot_sender.send_message(chat_id=CHANNEL_ID, text=chan_text, reply_markup=InlineKeyboardMarkup(chan_buttons), parse_mode=ParseMode.HTML)
    except: pass

    # إرسال للمستخدمين
    for user_id in TARGET_USERS:
        try:
            await bot_sender.send_message(chat_id=user_id, text=user_text, reply_markup=InlineKeyboardMarkup(user_buttons), parse_mode=ParseMode.HTML)
            await asyncio.sleep(0.3)
        except: continue

# --- استقبال الرسائل بنظام الأحداث (أفضل وأسرع) ---
@user_app.on_message(filters.group)
async def handle_new_message(client, message):
    text = message.text or message.caption
    if not text or (message.from_user and message.from_user.is_self):
        return

    found_district = analyze_message_by_districts(text)
    if found_district:
        print(f"✅ تم التقاط طلب في: {found_district}")
        await notify_all(found_district, message)

# --- خادم الويب للحفاظ على التشغيل ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"Bot Active")
    def log_message(self, format, *args): return

def run_health_server():
    server = HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), HealthCheckHandler)
    server.serve_forever()

if __name__ == "__main__":
    # تشغيل خادم الويب في خيط منفصل
    threading.Thread(target=run_health_server, daemon=True).start()
    
    print("🚀 الرادار يعمل الآن بنظام الاستماع الذكي...")
    user_app.run()
