# 1. استخدام نسخة بايثون الرسمية مع متصفح بلاي رايت مسبق التثبيت
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# 2. تعيين مجلد العمل داخل الحاوية
WORKDIR /app

# 3. نسخ ملف المتطلبات أولاً للاستفادة من الـ Cache
COPY requirements.txt .

# 4. تثبيت مكتبات البايثون
RUN pip install --no-cache-dir -r requirements.txt

# 5. نسخ بقية ملفات المشروع (main.py, index.html, إلخ)
COPY . .

# 6. تثبيت متصفح كروميوم مع تبعاته (سيثبت داخل الصورة)
RUN playwright install chromium --with-deps

# 7. إعداد متغيرات البيئة لضمان تشغيل FastAPI بشكل صحيح
ENV PORT=10000
EXPOSE 10000

# 8. أمر التشغيل النهائي باستخدام uvicorn
CMD ["sh", "-c", "uvicorn jaddahh:app --host 0.0.0.0 --port ${PORT}"]
