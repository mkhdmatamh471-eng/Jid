import asyncio
import threading
import sys
import os
import logging
import re  
from http.server import BaseHTTPRequestHandler, HTTPServer
from pyrogram import Client, filters 
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
import google.generativeai as genai
from datetime import datetime
from pyrogram.enums import ChatType

# --- إعداد السجلات ---
logging.basicConfig(level=logging.INFO)
# تقليل الضجيج في السجلات
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# --- استيراد الإعدادات ---
try:
    # تأكد من وجود ملف config.py وفيه المتغيرات المطلوبة
    from config import normalize_text, CITIES_DISTRICTS, BOT_TOKEN
    print("✅ تم تحميل الإعدادات بنجاح")
except Exception as e:
    print(f"❌ خطأ في تحميل ملف config.py: {e}")
    # إذا لم يكن الملف موجوداً، لن يتوقف البرنامج بل سنعتمد على متغيرات البيئة إذا أردت
    # sys.exit(1) 

# --- متغيرات البيئة ---
API_ID = os.environ.get("API_ID", "33888256")
API_HASH = os.environ.get("API_HASH", "bb1902689a7e203a7aedadb806c08854")
SESSION_STRING = os.environ.get("SESSION_STRING", "BAIFGAAAWH0qADVIqGjuDmtifoW-SQxSznz5ZhQjTbbPT2_wrX7IXCv95zqwku9kG4rpIf_xv3IDkt7CFUETnMEtUIff39Po9PwGgsiivLE1Mrbs6Ymw-h7qQap0oxSpSuIVRzWQT8_DWRJ8NGcTtp8VOJrZ7tjvjDMuVouYYd5ZmGNKry7QCQSRZuNCxc29IUC_eirR4KJKwC5IV1Ve5_Jq3PYYr8nsmiEvYauzrwftmivipkmg9CDyQfVxBfJmKi9WJuWQVvTqJWeIYYkBFLJmkcjOAKsej9fqzD4laRJIsKXaVxgfwmX5STeBpjBI7EPlMn9v0UvKQT49rYNQer0UyRSUWAAAAAH9nH9OAA")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDtF2lEZuEvI1hTFFrPRbGwwvj7ZocdPjs")

# --- إعدادات القنوات والمستخدمين ---
CHANNEL_ID = -1003843717541 
TARGET_USERS = [
    7996171713, 7513630480, 669659550, 6813059801, 632620058, 7093887960, 8024679997
]

# --- إعداد Gemini ---
genai.configure(api_key=GEMINI_API_KEY)
generation_config = {
  "temperature": 0.0, # صفر للدقة القصوى
  "top_p": 1.0,
  "max_output_tokens": 5,
}
ai_model = genai.GenerativeModel(
  model_name="gemini-1.5-flash", # الاسم المستقر
  generation_config=generation_config,
)

# --- عملاء تليجرام ---
user_app = Client("my_session", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH)
bot_sender = Bot(token=BOT_TOKEN)

# ---------------------------------------------------------
# قوائم الفلترة
# ---------------------------------------------------------
BLOCK_KEYWORDS = [
    "متواجد", "شغال الآن", "بخدمتكم", "أستقبل طلباتكم", "أوصل مشاوير", 
    "ارخص الاسعار", "بأسعار مناسبة", "واتساب", "للتواصل واتس", "يوجد لدينا توصيل",
    "سيارة حديثة", "فان عائلي", "سيارة نظيفة", "أسعارنا",
    "نقل عفش", "سطحة", "سطحه", "تأمين", "تفويض", "تجديد", "قرض", "تمويل", 
    "تسديد مخالفات", "استقدام", "خادمات", "شغالات", "معقب", "انجاز", "إنجاز",
    "عقار", "عقارات", "للبيع", "للايجار", "مخطط", "أرض", "ارض", "فلة", "شقة",
    "http", "t.me", ".com", "رابط", "انضم", "جروب", "قروب", "قناة", "اشترك",
    "استثمار", "زواج", "مسيار", "خطابه", "خطابة", "تعارف", "عذر طبي", "سكليف"
]

IRRELEVANT_TOPICS = [
    "تقويم اسنان", "خلع اسنان", "تركيبات", "عيادة", "عياده",
    "سمكري", "قطع غيار", "تشليح", "ورشة سيارات", "فحص دوري",
    "استفسار عن", "تنصحوني بـ", "أفضل دكتور", "مين جرب"
]

# ---------------------------------------------------------
# دوال الفحص اليدوي (تم التصحيح هنا)
# ---------------------------------------------------------
def manual_fallback_check_jeddah(clean_text):
    # 1. كلمات تدل على "نية الطلب"
    order_triggers = [
        "ابي", "ابغي", "أبغا", "ابغى", "محتاج", "مطلوب", "نبي", "مين", "بكم", 
        "يوديني", "يوصلني", "توديني", "توصيلة", "توصيله", "مشوار", "حق مشوار",
        "دحين", "حالا", "الآن", "مستعجل", "فينك", "في احد", "في أحد", "متوفر", 
        "موجود", "كباتن", "يا كابتن", "يا شباب", "سواق", "سائق", "مندوب", "يطلع", # ✅ تم إضافة الفاصلة هنا
        "الين", "لين", "لغاية", "رايح", "خارج", "نازل", "من", "إلى", "الى"
    ]

    # 2. وجهات ومعالم جدة
    jeddah_keywords = [
        "الحمدانية", "الفلاح", "الرحيلي", "أبحر", "ابحر", "البساتين", "المرجان", 
        "النعيم", "النهضة", "المنار", "السامر", "الأجواد", "الصفا", "المروة", 
        "الروضة", "الخالدية", "الزهراء", "السلامة", "البوادي", "النزهة",
        "البلد", "التحلية", "شارع فلسطين", "شارع حراء", "شارع السبعين", "الفيصلية", 
        "الرويس", "حي الجامعة", "السليمانية", "الفيحاء", "الثغر", "الروابي", 
        "السنابل", "الأجاويد", "حي العدل", "حي الأمير فواز", "الخمرة", "القوزين",
        "المطار", "مطار الملك عبدالعزيز", "الصالة الشمالية", "صالة 1", "مطار جده",
        "قطار الحرمين", "محطة القطار", "موقع القطار", "الواجهة البحرية", "الكورنيش", 
        "الأندلس مول", "عزيز مول", "الياسمين مول", "الردسي", "ريدسي", "العرب مول", 
        "مجمع العرب", "هيفاء مول", "السلام مول", "الجامعة", "عفت", "دار الحكمة", 
        "بتروجيمن", "تاتش", "سليمان فقيه", "المستشفى الطبي", "التخصصي", "الحرس", "جدة", "جده"
    ]
    
    # 3. فحص "الطلب الصريح"
    has_order = any(w in clean_text for w in order_triggers)
    has_keyword = any(w in clean_text for w in jeddah_keywords)
    
    # 4. فحص "المسار"
    has_route = "من" in clean_text and any(x in clean_text for x in [" الى", " إلى", " لـ", " للمطار", " للبلد", " لحي", " الين", " لين"])
    
    # 5. فحص "السؤال عن السعر" 
    is_asking_price = "بكم" in clean_text and any(x in clean_text for x in ["مشوار", "توصيل", "يوديني", "توديني"])

    return (has_order and has_keyword) or has_route or is_asking_price

# ---------------------------------------------------------
# المحرك الهجين (AI + Manual)
# ---------------------------------------------------------
async def analyze_message_hybrid(text):
    if not text or len(text) < 5 or len(text) > 400: 
        return False

    clean_text = normalize_text(text)
    
    # 1. القتل الفوري للكلمات المحظورة
    if any(k in clean_text for k in BLOCK_KEYWORDS + IRRELEVANT_TOPICS): 
        # print(f"🚫 تم حظر الرسالة فوراً") # اختياري: إخفاء الطباعة لتنظيف السجلات
        return False

    # 2. الفحص اليدوي أولاً (للسرعة وتوفير التكلفة)
    # ✅ تم التعديل لاستخدام دالة جدة بدلاً من الدالة العامة
    if manual_fallback_check_jeddah(clean_text):
        print(f"✅ تم السحب بالفحص اليدوي (جدة): {clean_text[:20]}...")
        return True

    # 3. الذكاء الاصطناعي (Gemini)
    prompt = f"""
    Role: Elite Traffic Controller for Jeddah.
    Task: Reply 'YES' if this is a CUSTOMER request for a ride/delivery in Jeddah. Reply 'NO' for drivers/ads.
    Text: "{text}"
    Reply ONLY YES or NO.
    """

    try:
        response = await asyncio.to_thread(ai_model.generate_content, prompt)
        result = response.text.strip().upper()
        if "YES" in result:
            print(f"✅ قبول AI: {clean_text[:20]}...")
            return True
        else:
            return False

    except Exception as e:
        print(f"⚠️ تجاوز AI: {e}")
        return False # تم الفحص اليدوي مسبقاً، لذا نرجع False هنا

# ---------------------------------------------------------
# دوال الإرسال
# ---------------------------------------------------------
async def notify_users(detected_district, original_msg):
    content = original_msg.text or original_msg.caption
    if not content: return

    try:
        customer = original_msg.from_user
        if not customer or not customer.id: return

        # رابط مباشر
        gateway_url = f"https://t.me/{original_msg.chat.username}/{original_msg.id}" if original_msg.chat.username else f"tg://user?id={customer.id}"
        
        buttons_list = [[InlineKeyboardButton("💬 الذهاب للرسالة", url=gateway_url)]]
        keyboard = InlineKeyboardMarkup(buttons_list)

        alert_text = (
            f"🎯 <b>طلب جديد (جدة)!</b>\n\n"
            f"📍 <b>المنطقة:</b> {detected_district}\n"
            f"👤 <b>العميل:</b> {customer.first_name}\n"
            f"📝 <b>النص:</b>\n<i>{content}</i>"
        )

        for user_id in TARGET_USERS:
            try:
                await bot_sender.send_message(
                    chat_id=user_id,
                    text=alert_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass # تجاهل الأخطاء الفردية

    except Exception as e:
        print(f"❌ خطأ notify_users: {e}")

async def notify_channel(detected_district, original_msg):
    content = original_msg.text or original_msg.caption
    if not content: return

    try:
        customer = original_msg.from_user
        if not customer: return

        direct_url = f"tg://user?id={customer.id}"
        buttons = [
            [InlineKeyboardButton("💬 مراسلة العميل مباشرة", url=direct_url)],
            # [InlineKeyboardButton("💳 اشتراك", url="https://t.me/Servecestu")]
        ]
        keyboard = InlineKeyboardMarkup(buttons)

        alert_text = (
            f"🎯 <b>طلب جديد!</b>\n"
            f"📍 <b>المنطقة:</b> {detected_district}\n"
            f"👤 <b>العميل:</b> {customer.first_name}\n\n"
            f"📝 <i>{content}</i>"
        )

        await bot_sender.send_message(
            chat_id=CHANNEL_ID,
            text=alert_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        print(f"📢 تم النشر بالقناة: {detected_district}")

    except Exception as e:
        print(f"❌ خطأ notify_channel: {e}")

# ---------------------------------------------------------
# المعالج الرئيسي (Listener)
# ---------------------------------------------------------
@user_app.on_message(filters.text & filters.group & ~filters.me) # ~filters.me لتجنب سحب رسائلك
async def message_handler(client, msg):
    try:
        text = msg.text or msg.caption
        if not text: return

        # التحليل
        if await analyze_message_hybrid(text):
            # محاولة استخراج اسم الحي للعرض
            found_d = "جدة"
            # (يمكنك إضافة كود مطابقة الأحياء هنا إذا رغبت)

            await asyncio.gather(
                notify_users(found_d, msg),
                notify_channel(found_d, msg)
            )

    except Exception as e:
        logging.error(f"Error in handler: {e}")

# ---------------------------------------------------------
# التشغيل وخادم الصحة
# ---------------------------------------------------------
def run_health_server():
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.wfile.write(b"ALIVE")
        def log_message(self, format, *args): return

    try:
        server = HTTPServer(('0.0.0.0', 10000), HealthHandler)
        print("🌍 Health Server running on port 10000")
        server.serve_forever()
    except Exception as e:
        print(f"❌ Health Server failed: {e}")

async def main():
    print("🚀 بدء تشغيل الرادار (جدة)...")
    await user_app.start()
    print("✅ اليوزر بوت متصل!")
    
    from pyrogram.methods.utilities.idle import idle
    await idle()
    
    await user_app.stop()

if __name__ == "__main__":
    # تشغيل خادم الصحة
    threading.Thread(target=run_health_server, daemon=True).start()
    
    # تشغيل البوت
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("👋 إيقاف.")
    except Exception as e:
        print(f"⚠️ خطأ فادح: {e}")
        sys.exit(1)
