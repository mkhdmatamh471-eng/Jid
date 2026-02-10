import asyncio
import threading
import sys
import os
import logging
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pyrogram import Client
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from datetime import datetime

# --- إعداد السجلات ---
logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# --- استيراد الإعدادات ---
try:
    from config import normalize_text, CITIES_DISTRICTS, BOT_TOKEN
    print("✅ تم تحميل الإعدادات بنجاح (الاعتماد الآن على قائمة الأحياء)")
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

# ---------------------------------------------------------
# قوائم الفلترة (الكلمات الممنوعة)
# ---------------------------------------------------------
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
# ---------------------------------------------------------
# محرك الفحص المعتمد على الأحياء (بدون AI)
# ---------------------------------------------------------
def analyze_message_by_districts(text):
    """
    تقوم هذه الدالة بفحص النص بناءً على الأحياء والكلمات الدلالية.
    تعود بـ (اسم الحي) إذا كان الطلب صالحاً، أو None إذا لم يكن كذلك.
    """
    if not text or len(text) < 5: return None
    
    clean_text = normalize_text(text)

    # 1. استبعاد الكلمات المحظورة فوراً
    if any(k in clean_text for k in BLOCK_KEYWORDS): return None
    if any(k in clean_text for k in IRRELEVANT_TOPICS): return None

    # 2. البحث عن اسم حي من القائمة
    detected_district = None
    for city, districts in CITIES_DISTRICTS.items():
        for d in districts:
            if normalize_text(d) in clean_text:
                detected_district = d
                break
        if detected_district: break
    
    # إذا لم نجد حي، نتوقف هنا
    if not detected_district: return None

    # 3. التأكد من وجود نية (طلب) لضمان عدم سحب السوالف
    order_indicators = ["ابي", "ابغي", "محتاج", "مطلوب", "توصيل", "مشوار", "يوديني", "يوصلني", "بكم", "من", "إلى"]
    if any(word in clean_text for word in order_indicators):
        return detected_district

    return None

# ---------------------------------------------------------
# وظائف الإرسال
# ---------------------------------------------------------
async def notify_users(detected_district, original_msg):
    content = original_msg.text or original_msg.caption
    customer = original_msg.from_user
    bot_username = "Mishweribot" 
    gateway_url = f"https://t.me/{bot_username}?start=chat_{customer.id if customer else 0}"

    buttons = [[InlineKeyboardButton("💬 مراسلة العميل (عبر البوت)", url=gateway_url)]]
    alert_text = (
        f"🎯 <b>طلب جديد تم التقاطه!</b>\n\n"
        f"📍 <b>المنطقة:</b> {detected_district}\n"
        f"👤 <b>العميل:</b> {customer.first_name if customer else 'مخفي'}\n"
        f"📝 <b>النص:</b>\n<i>{content}</i>"
    )

    for user_id in TARGET_USERS:
        try:
            await bot_sender.send_message(chat_id=user_id, text=alert_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
            await asyncio.sleep(0.3)
        except: continue

async def notify_channel(detected_district, original_msg):
    content = original_msg.text or original_msg.caption
    customer_id = original_msg.from_user.id if original_msg.from_user else 0
    bot_username = "Mishweribot" 

    gate_contact = f"https://t.me/{bot_username}?start=contact_{customer_id}"
    buttons = [
        [InlineKeyboardButton("💬 مراسلة العميل (للمشتركين)", url=gate_contact)],
        [InlineKeyboardButton("💳 للاشتراك وتفعيل الحساب", url="https://t.me/Servecestu")]
    ]

    alert_text = (
        f"🎯 <b>طلب مشوار جديد</b>\n\n"
        f"📍 <b>المنطقة:</b> {detected_district}\n"
        f"📝 <b>التفاصيل:</b>\n<i>{content}</i>\n\n"
        f"⚠️ <i>الروابط أعلاه تفتح للمشتركين فقط.</i>"
    )

    try:
        await bot_sender.send_message(chat_id=CHANNEL_ID, text=alert_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
    except: pass

# ---------------------------------------------------------
# الرادار الرئيسي
# ---------------------------------------------------------
async def start_radar():
    await user_app.start()
    print("🚀 الرادار يعمل الآن بالاعتماد على قائمة الأحياء...")
    
    last_processed = {}

    while True:
        try:
            await asyncio.sleep(3) # فحص كل 3 ثواني لسرعة الاستجابة

            async for dialog in user_app.get_dialogs(limit=40):
                if str(dialog.chat.type).upper() not in ["GROUP", "SUPERGROUP"]: continue
                chat_id = dialog.chat.id

                async for msg in user_app.get_chat_history(chat_id, limit=1):
                    if chat_id in last_processed and msg.id <= last_processed[chat_id]: continue
                    last_processed[chat_id] = msg.id

                    text = msg.text or msg.caption
                    if not text or (msg.from_user and msg.from_user.is_self): continue

                    # الفحص بناءً على الأحياء
                    found_district = analyze_message_by_districts(text)

                    if found_district:
                        await notify_users(found_district, msg)
                        await notify_channel(found_district, msg)
                        print(f"✅ تم التقاط طلب في حي: {found_district}")

        except Exception as e:
            await asyncio.sleep(5)

# --- خادم الويب ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"Bot Active - Neighborhood Radar")
    def log_message(self, format, *args): return

if __name__ == "__main__":
    threading.Thread(target=lambda: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), HealthCheckHandler).serve_forever(), daemon=True).start()
    asyncio.run(start_radar())
