import os
import logging
import threading
import asyncio # أضفنا هذا السطر
from flask import Flask
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from pypdf import PdfReader

# --- إعداد Flask ---
server = Flask(__name__)

@server.route('/')
def home():
    return "Bot is Running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# --- إعدادات التسجيل ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- قائمة المديرين (حسب تعليماتك) ---
ADMIN_IDS = [7996171713, 7513630480, 8549859150]

# --- مفاتيح الـ API ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

user_context = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("عذراً، هذا البوت مخصص للمديرين المعتمدين فقط. 🚫")
        return
    
    await update.message.reply_text("👋 أهلاً بك أدمن! أرسل لي المحاضرة (نص أو PDF) لأقوم بمعالجتها.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return

    chat_id = update.message.chat_id
    text_content = ""

    if update.message.text:
        text_content = update.message.text
    elif update.message.document and update.message.document.file_name.lower().endswith('.pdf'):
        msg = await update.message.reply_text("⏳ جاري استخراج النص من ملف PDF...")
        try:
            file = await context.bot.get_file(update.message.document.file_id)
            path = f"{chat_id}.pdf"
            await file.download_to_drive(path)
            reader = PdfReader(path)
            for page in reader.pages:
                text_content += page.extract_text() + "\n"
            os.remove(path)
            await msg.delete()
        except Exception as e:
            await update.message.reply_text(f"خطأ في معالجة الملف: {e}")
            return

    if text_content:
        user_context[chat_id] = {"text": text_content[:20000]}
        keyboard = [
            [InlineKeyboardButton("📝 تلخيص المحاضرة", callback_data="action_sum")],
            [InlineKeyboardButton("❓ إنشاء أسئلة (Quiz)", callback_data="action_quiz")]
        ]
        await update.message.reply_text("تم استلام المحتوى. ماذا تريد أن أفعل؟", reply_markup=InlineKeyboardMarkup(keyboard))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    
    if chat_id not in user_context:
        await query.answer("انتهت الجلسة، أرسل الملف مجدداً.")
        return

    await query.answer()
    content = user_context[chat_id]["text"]
    
    status_msg = await query.message.reply_text("⏳ جاري معالجة طلبك عبر ذكاء Gemini...")

    try:
        # تشغيل طلب Gemini في Thread منفصل لعدم تجميد البوت
        loop = asyncio.get_event_loop()
        
        if query.data == "action_sum":
            prompt = f"لخص هذا النص الأكاديمي بالعربية في نقاط واضحة:\n{content}"
        else:
            prompt = f"صغ 5 أسئلة اختيار من متعدد مع الحل بناءً على هذا النص:\n{content}"

        # استخدام run_in_executor لضمان عدم توقف الـ Event Loop
        response = await loop.run_in_executor(None, lambda: model.generate_content(prompt))
        
        await status_msg.edit_text(response.text)
    except Exception as e:
        await status_msg.edit_text(f"❌ حدث خطأ أثناء الاتصال بـ Gemini: {e}")

def main():
    # تشغيل Flask للتوافق مع Render
    threading.Thread(target=run_flask, daemon=True).start()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    print("البوت يعمل بنجاح...")
    app.run_polling()

if __name__ == '__main__':
    main()
