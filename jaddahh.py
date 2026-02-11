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
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDtF2lEZuEvI1hTFFrPRbGwwvj7ZocdPjs")

# ---------------------------------------------------------
# 🛠️ [تعديل 1] قائمة المستخدمين الذين سيستلمون الطلبات
# ضع الـ IDs الخاصة بهم هنا (أرقام فقط)
# ---------------------------------------------------------
# 🛠️ قائمة الـ IDs المحدثة الذين سيستلمون الطلبات في الخاص (مفتوحة)
CHANNEL_ID = -1003843717541 
 # <--- ضع الآيديات الحقيقية هنا

TARGET_USERS = [
    7996171713, 7513630480, 669659550, 6813059801, 632620058, 7093887960, 8024679997
]




# --- إعداد Gemini 1.5 Flash ---
genai.configure(api_key=GEMINI_API_KEY)
generation_config = {
  "temperature": 0.1,
  "top_p": 0.95,
  "top_k": 40,
  "max_output_tokens": 5,
}
ai_model = genai.GenerativeModel(
  model_name="gemini-1.5-flash",
  generation_config=generation_config,
)

# --- عملاء تليجرام ---
user_app = Client("my_session", session_string=SESSION_STRING, api_id=API_ID, api_hash=API_HASH)
bot_sender = Bot(token=BOT_TOKEN)

# ---------------------------------------------------------
# قوائم الفلترة (كما هي في كودك الأصلي)
# ---------------------------------------------------------
# قائمة 1: كلمات تدل أن المرسل سائق أو إعلان أو مواضيع محظورة (حظر فوري)
BLOCK_KEYWORDS = [
    # كلمات تدل على أن المرسل "سائق" يعرض خدمته
    "متواجد الآن", "شغال الآن", "جاهز للتوصيل", "سيارة نظيفة", "أسعارنا", 
    "دربك سمح", "بخدمتكم", "استقبل طلباتكم", "أستقبل طلباتكم", "أوصل مشاوير", 
    "بأرخص الأسعار", "ارخص الاسعار", "بأسعار مناسبة", "واتساب", "للتواصل واتس",
    "فان عائلي", "سيارة حديثة", "سواق خاص جاهز", "يوجد لدينا توصيل",

    # إعلانات الخدمات الأخرى (بعيداً عن المشاوير)
    "نقل عفش", "نقل بضائع", "سطحة", "سطحه", "دباب نقل", "تأمين", "تفويض", 
    "تجديد", "قرض", "تمويل", "تسديد مخالفات", "استقدام", "خادمات", "شغالات",
    "معقب", "انجاز", "إنجاز", "تعديل مهنة", "اسقاط", "كفيل", "نقل كفالة",

    # إعلانات العقارات
    "عقار", "عقارات", "للبيع", "للايجار", "للإيجار", "مخطط", "أرض", "ارض", 
    "فلة", "فله", "شقة", "شقه", "دور للبيع", "صك", "إفراغ", "الوساطة العقارية",

    # الروابط والسبام
    "http", "t.me", ".com", "رابط", "انضم", "جروب", "قروب", "قناة", "اشترك",

    # مواضيع اجتماعية
    "استثمار", "زواج", "مسيار", "خطابه", "خطابة", "تعارف"
]


# قائمة 2: كلمات خارج السياق (طبي، أعذار، استفسارات عامة) - حظر فوري
IRRELEVANT_TOPICS = [
    # طبي (أعذار ومراجعات) - لاحظ حذفنا كلمة "مستشفى" لأن الركاب يطلبون مشاوير لها
    "عذر طبي", "سكليف", "سكليفات", "اجازة مرضية", "إجازة مرضية", 
    "تقويم اسنان", "خلع اسنان", "تنظيف اسنان", "تركيبات", "عيادة", "عياده",
    
    # ميكانيكا وورش
    "سمكري", "قطع غيار", "تشليح", "ورشة سيارات", "ورشه سيارات", "فحص دوري",
    
    # استفسارات عامة لا تتطلب مشوار
    "استفسار عن", "تنصحوني بـ", "أفضل دكتور", "افضل دكتور", "مين جرب"
]


# ---------------------------------------------------------
# 2. المحرك الهجين (Hybrid Engine)
# ---------------------------------------------------------
async def analyze_message_hybrid(text):
    if not text or len(text) < 5 or len(text) > 400: 
        return False

    clean_text = normalize_text(text)
    
    # 1. القتل الفوري للكلمات المحظورة (لتوفير استهلاك الـ API)
    if any(k in clean_text for k in BLOCK_KEYWORDS + IRRELEVANT_TOPICS): 
        print(f"🚫 تم حظر الرسالة فوراً (كلمات محظورة)")
        return False

    # 2. البرومبت الاحترافي المخصص لجدة
    # تم تحديث اسم النموذج ليتوافق مع الإصدارات المستقرة
        # البرومبت الاحترافي المطور لجدة (الإصدار الشامل لجميع الأحياء)
    prompt = f"""
    Role: You are an elite AI Traffic Controller for the 'Jeddah Live Dispatch' system. 
    Objective: Identify REAL CUSTOMERS in Jeddah while ignoring drivers, ads, and spam.

    [CORE LOGIC]
    Return 'YES' ONLY if the sender is a HUMAN CUSTOMER seeking a ride or delivery.
    Return 'NO' if it's a driver offering service, an ad, or irrelevant talk.

    [📍 COMPREHENSIVE JEDDAH GEOGRAPHY]
    Recognize any mention of these areas as a potential Jeddah request:
    - North: (Obhur Al-Shamaliyah/Janubiyah, Al-Abruq, Al-Basateen, Al-Mohammadiyah, Al-Shati, Al-Naeem, Al-Zahra, Al-Salama, Al-Bawadi, Al-Rawdah, Al-Faisaliah, Al-Reheli, Al-Hamdania, Al-Salhiya, Al-Falah).
    - Central: (Al-Safa, Al-Marwah, Al-Rehab, Al-Kandarah, Al-Aziziyah, Al-Mushrifah, Al-Rehab, Al-Baghdadia, Al-Ruwaiss, Al-Sharafiyah, Al-Wurud).
    - South & East: (Al-Balad, Al-Hindawiya, Al-Thualba, Al-Waziriyah, Al-Amir Fawaz, Al-Iskan, Al-Khumra, Al-Sanaiya, Al-Ajawid, Al-Samer, Al-Manar, Al-Adl, Al-Abaid, Al-Harazat).
    - Landmarks: (King Abdulaziz Airport KAIA, T1, North Terminal, Jeddah Islamic Port, Haramain Train Station Sulaymaniyah, Jeddah Corniche, Waterfront, KAU, Jeddah Park, Red Sea Mall, Mall of Arabia, Al-Andalus Mall, Al-Salam Mall).

    [✅ CLASSIFY AS 'YES' (CUSTOMER INTENT)]
    - Direct: "أبغا سواق"، "مطلوب كابتن"، "مين فاضي يوصلني"، "في أحد حول حي..."
    - Routes: "مشوار من الصفا للتحلية"، "من المطار لأبحر"، "بكم توديني الرد سي؟"
    - Slang/Hijazi: (أبغى، أبغا، فينك، كباتن، يوديني، يوصلني، دحين، حق مشوار، توصيلة).
    - Delivery: "أحتاج مندوب"، "توصيل غرض"، "أبغا أحد يجيب لي طلب من..."

    [❌ CLASSIFY AS 'NO' (DRIVER/SPAM/ADS)]
    - Driver offers: "شغال الآن"، "موجود بجدة"، "سيارة نظيفة"، "توصيل مطار بأرخص الأسعار".
    - Keywords: (متواجد، متاح، أسعارنا، استقدام، عقار، سكليف، عذر طبي، قرض، باقات).

    Input Text: "{text}"

    FINAL ANSWER (Reply ONLY with 'YES' or 'NO'):
    """


    try:
        # تأكد من تعريف ai_model باستخدام "gemini-1.5-flash-latest" في بداية الملف
        response = await asyncio.to_thread(ai_model.generate_content, prompt)
        
        # تنظيف النتيجة من أي زيادات
        result = response.text.strip().upper().replace(".", "").replace("'", "")
        
        if "YES" in result:
            print(f"✅ ذكاء اصطناعي: قبول طلب لجدة")
            return True
        else:
            return False

    except Exception as e:
        # في حال فشل الـ AI (مثل خطأ 404 أو ضغط الشبكة)، نعتمد الفحص اليدوي كخطة بديلة
        print(f"⚠️ تجاوز AI (فشل الاتصال): {e}")
        return manual_fallback_check(clean_text)

def manual_fallback_check(clean_text):
    # كلمات تدل على الطلب في جدة
    order_triggers = ["ابي", "ابغي", "أبغا", "محتاج", "مطلوب", "نبي", "مين يوديني"]
    jeddah_keywords = ["سواق", "كابتن", "مشوار", "توصيل", "جدة", "جده"]
    
    has_order = any(w in clean_text for w in order_triggers)
    has_keyword = any(w in clean_text for w in jeddah_keywords)
    
    # فحص نمط "من ... إلى" الشهير
    has_route = "من" in clean_text and ("الى" in clean_text or "إلى" in clean_text or "لـ" in clean_text)
    
    return (has_order and has_keyword) or has_route

def manual_fallback_check_jeddah(clean_text):
    # 1. كلمات تدل على "نية الطلب" (Intent) - لهجة أهل جدة والغربية
    order_triggers = [
        "ابي", "ابغي", "أبغا", "محتاج", "مطلوب", "نبي", "مين", 
        "في احد", "فينك", "بكم", "يوديني", "يوصلني", "توصيله", "حق مشوار", "دحين"
    ]
    
    # 2. وجهات ومعالم جدة (Context)
    jeddah_keywords = [
        "سواق", "كابتن", "مشوار", "توصيل", "جدة", "جده", 
        "المطار", "البلد", "التحلية", "الحمدانية", "أبحر", "السنابل", 
        "السامر", "الصفا", "الروضة", "الردسي", "الواجهة", "الكورنيش", 
        "قطار الحرمين", "جامعة الملك عبدالعزيز", "عزيز مول", "مطار الملك عبدالعزيز"
    ]
    
    # 3. فحص "الطلب الصريح" (دمج نية الطلب مع كلمة تدل على جدة)
    has_order = any(w in clean_text for w in order_triggers)
    has_keyword = any(w in clean_text for w in jeddah_keywords)
    
    # 4. فحص "المسار" (من وإلى) - مخصص لطرق جدة
    # يدعم: "من المطار للحمدانية"، "من الصفا الى التحلية"
    has_route = "من" in clean_text and any(x in clean_text for x in [" الى", " إلى", " لـ", " للمطار", " للبلد", " لحي"])
    
    # 5. فحص "السؤال عن السعر" 
    is_asking_price = "بكم" in clean_text and any(x in clean_text for x in ["مشوار", "توصيل", "يوديني", "توديني"])

    # النتيجة: سحب الطلب إذا تحقق أي شرط
    return (has_order and has_keyword) or has_route or is_asking_price


# ---------------------------------------------------------
# 3. [تعديل 2] دالة الإرسال للمستخدمين المحددين
# ---------------------------------------------------------
async def notify_users(detected_district, original_msg):
    content = original_msg.text or original_msg.caption
    if not content: return

    try:
        customer = original_msg.from_user
        # ✅ التحقق من وجود العميل لتجنب انهيار الكود
        if not customer or not customer.id:
            print("⚠️ تعذر جلب ID العميل، سيتم تخطي الإرسال.")
            return

        # ✅ تأكد من اليوزر الصحيح (Mishweriibot أم Mishwariibot)
        bot_username = "Mishweribot" 
        
        # ✅ استخدام متغير محمي للآيدي
        customer_id = customer.id
        gateway_url = f"https://t.me/{bot_username}?start=direct_{customer_id}"

        buttons_list = [
            [InlineKeyboardButton("💬 مراسلة العميل الآن", url=gateway_url)],
        ]

        keyboard = InlineKeyboardMarkup(buttons_list)

        # ✅ تنسيق النص
        alert_text = (
            f"🎯 <b>طلب جديد تم التقاطه!</b>\n\n"
            f"📍 <b>المنطقة:</b> {detected_district}\n"
            f"👤 <b>اسم العميل:</b> {customer.first_name}\n"
            f"📝 <b>نص الطلب:</b>\n<i>{content}</i>"
        )

        # ✅ إرسال الرسائل للمستخدمين المحددين
        for user_id in TARGET_USERS:
            try:
                await bot_sender.send_message(
                    chat_id=user_id,
                    text=alert_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e_user:
                print(f"⚠️ فشل الإرسال للمستخدم {user_id}: {e_user}")

    except Exception as e:
        print(f"❌ خطأ عام في دالة الإرسال للمستخدمين: {e}")

async def notify_channel(detected_district, original_msg):
    content = original_msg.text or original_msg.caption
    if not content: return

    try:
        customer = original_msg.from_user
        if not customer: return

        # ✅ إنشاء رابط المراسلة المباشر مع الراكب (بدور وسيط)
        # سيفتح حساب الراكب فوراً عند ضغط السائق
        direct_url = f"tg://user?id={customer.id}"

        buttons = [
            [InlineKeyboardButton("💬 مراسلة العميل مباشرة", url=direct_url)],
            [InlineKeyboardButton("💳 للاشتراك وتفعيل الحساب", url="https://t.me/Servecestu")]
        ]

        keyboard = InlineKeyboardMarkup(buttons)

        # ✅ نص الرسالة بدون وقت ومع إزاحة مضبوطة
        alert_text = (
            f"🎯 <b>طلب جديد تم التقاطه!</b>\n\n"
            f"📍 <b>المنطقة:</b> {detected_district}\n"
            f"👤 <b>اسم العميل:</b> {customer.first_name}\n"
            f"📝 <b>نص الطلب:</b>\n<i>{content}</i>"
        )

        await bot_sender.send_message(
            chat_id=CHANNEL_ID,
            text=alert_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        print(f"✅ تم الإرسال للقناة برابط مباشر: {detected_district}")

    except Exception as e:
        print(f"❌ خطأ إرسال للقناة: {e}")


# --- [تطوير] معالج الرسائل الذكي ---
@user_app.on_message(filters.text & filters.group)
async def message_handler(client, msg):
    try:
        text = msg.text or msg.caption
        if not text or len(text) < 5:
            return

        # 1. التحليل الهجين (فلاتر + ذكاء اصطناعي)
        is_valid_order = await analyze_message_hybrid(text)

        if is_valid_order:
            # محاولة تحديد المنطقة من النص
            found_d = "جدة - عام"
            text_c = normalize_text(text)
            for city, districts in CITIES_DISTRICTS.items():
                for d in districts:
                    if normalize_text(d) in text_c:
                        found_d = d
                        break

            # 2. إرسال الإشعارات (استخدام asyncio.gather للسرعة)
            await asyncio.gather(
                notify_users(found_d, msg),
                notify_channel(found_d, msg)
            )
            logging.info(f"✅ تم تحويل طلب من: {msg.chat.title if msg.chat else 'Unknown'}")

    except Exception as e:
        logging.error(f"⚠️ خطأ في معالجة الرسالة: {e}")

# ---------------------------------------------------------
# 4. الرادار الرئيسي
# ---------------------------------------------------------
# --- [تطوير] معالج الرسائل الجديد (المستمع) ---
# هذا المعالج سيعمل تلقائياً عند وصول أي رسالة في المجموعات المشترك بها اليوزر بوت
# تأكد من استيراد ChatType في بداية الملف إذا لم يكن موجوداً

async def start_radar():
    print("🚀 بدء تشغيل الرادار...")
    try:
        # 1. تشغيل العميل
        await user_app.start()
        print("✅ تم اتصال اليوزر بوت بنجاح")

        # 2. 🔄 القراءة التلقائية للمجموعات (تحديث الكاش)
        print("⏳ جاري تحديث قائمة المجموعات...")
        group_count = 0
        async for dialog in user_app.get_dialogs():
            if dialog.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                group_count += 1
        
        print(f"✅ الرادار يراقب الآن {group_count} مجموعة.")

        # 3. 🟢 تفعيل وضع الانتظار المستمر (Idle)
        # هذا السطر ضروري جداً لكي يعمل @user_app.on_message
        from pyrogram.methods.utilities.idle import idle
        await idle()

    except Exception as e:
        print(f"❌ خطأ في الرادار: {e}")
    finally:
        if user_app.is_connected:
            await user_app.stop()

# --- كلاس ودالة خادم الصحة (Health Check) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Running")
    
    # لإيقاف ظهور سجلات الخادم المزعجة في التيرمينال
    def log_message(self, format, *args): 
        return

def run_health_server():
    # نستخدم البورت الذي يحدده Render أو 10000 كاحتياطي
    port = int(os.environ.get("PORT", 10000))
    print(f"🌍 تشغيل خادم الصحة على المنفذ: {port}")
    httpd = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    httpd.serve_forever()

# --- التشغيل الرئيسي ---
if __name__ == "__main__":
    # 1. تشغيل خادم الويب في خيط منفصل (Thread)
    # الآن الدالة run_health_server موجودة ولن يظهر خطأ
    threading.Thread(target=run_health_server, daemon=True).start()
    
    # 2. إعداد حلقة الأحداث (Loop) للرادار
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # 3. تشغيل الرادار
    try:
        loop.run_until_complete(start_radar())
    except (KeyboardInterrupt, SystemExit):
        print("👋 تم إيقاف الرادار يدوياً")
    except Exception as e:
        print(f"⚠️ خطأ غير متوقع في التشغيل: {e}")
