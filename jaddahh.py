import os
import logging
import threading
import asyncio
from flask import Flask
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from pypdf import PdfReader

# --- إعداد Flask للعمل على Render ---
server = Flask(__name__)

@server.route('/')
def home():
    return "Bot is Running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# --- إعدادات التسجيل ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- قائمة المديرين (Admin IDs) ---
ADMIN_IDS = [7996171713, 7513630480, 8549859150]

# --- مفاتيح الـ API من متغيرات البيئة ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# تهيئة عميل Groq
groq_client = Groq(api_key=GROQ_API_KEY)

user_context = {}

# دالة معالجة النصوص عبر Groq (Llama 3)
async def get_ai_response(prompt):
    loop = asyncio.get_event_loop()
    # تشغيل طلب الـ API في خيط منفصل لضمان عدم تعليق البوت
    completion = await loop.run_in_executor(None, lambda: groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
    ))
    return completion.choices[0].message.content

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("عذراً، هذا البوت مخصص للمديرين فقط. 🚫")
        return
    await update.message.reply_text("👋 أهلاً بك أدمن! أرسل لي نصاً أو ملف PDF للمحاضرة.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return

    chat_id = update.message.chat_id
    text_content = ""

    if update.message.text:
        text_content = update.message.text
    elif update.message.document and update.message.document.file_name.lower().endswith('.pdf'):
        msg = await update.message.reply_text("⏳ جاري استخراج النص من الـ PDF...")
        try:
            file = await context.bot.get_file(update.message.document.file_id)
            path = f"{chat_id}.pdf"
            await file.download_to_drive(path)
            reader = PdfReader(path)
            for page in reader.pages:
                text_content += (page.extract_text() or "") + "\n"
            os.remove(path)
            await msg.delete()
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ في الملف: {e}")
            return

    if text_content.strip():
        user_context[chat_id] = {"text": text_content[:25000]} # سعة Llama كبيرة
        keyboard = [
            [InlineKeyboardButton("📝 تلخيص المحاضرة", callback_data="action_sum")],
            [InlineKeyboardButton("❓ إنشاء أسئلة (Quiz)", callback_data="action_quiz")]
        ]
        await update.message.reply_text("المحتوى جاهز، اختر العملية المطلوبة:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("⚠️ لم أتمكن من العثور على نص صالح.")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    
    if chat_id not in user_context:
        await query.answer("الجلسة قديمة، أرسل الملف مجدداً.")
        return

    await query.answer()
    content = user_context[chat_id]["text"]
    status_msg = await query.message.reply_text("⏳ جاري المعالجة عبر ذكاء Groq (Llama 3)...")

    try:
        if query.data == "action_sum":
            prompt = f"قم بتلخيص النص التالي باللغة العربية بأسلوب أكاديمي مرتب في نقاط:\n\n{content}"
        else:
            prompt = f"بناءً على النص التالي، قم بصياغة 5 أسئلة اختيار من متعدد (MCQ) باللغة العربية مع تزويدي بالإجابات الصحيحة في النهاية:\n\n{content}"

        response_text = await get_ai_response(prompt)
        await status_msg.edit_text(response_text)
    except Exception as e:
        await status_msg.edit_text(f"❌ حدث خطأ في الاتصال: {str(e)}")

def main():
    # تشغيل Flask كخلفية لـ Render
    threading.Thread(target=run_flask, daemon=True).start()

    # إعداد تطبيق التلجرام
    if not TELEGRAM_TOKEN:
        print("خطأ: لم يتم العثور على TELEGRAM_TOKEN في متغيرات البيئة!")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    print("البوت يعمل الآن باستخدام Groq API...")
    app.run_polling()

if __name__ == '__main__':
    main()
