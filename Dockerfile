# 1. استخدام نسخة بايثون النحيفة (Slim) لتقليل حجم الصورة وسرعة التشغيل
FROM python:3.10-slim

# 2. تعيين مجلد العمل داخل الحاوية
WORKDIR /app

# 3. تثبيت التبعات الضرورية للنظام (مهمة لـ psycopg2 وبعض مكتبات التشفير)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. نسخ ملف المتطلبات أولاً
COPY requirements.txt .

# 5. تثبيت مكتبات البايثون (بدون بلاي رايت)
RUN pip install --no-cache-dir -r requirements.txt

# 6. نسخ بقية ملفات المشروع (jaddahh.py, index.html, إلخ)
COPY . .

# 7. إعداد متغيرات البيئة لضمان تشغيل FastAPI بشكل صحيح
ENV PORT=10000
ENV PYTHONUNBUFFERED=1
EXPOSE 10000

# 8. أمر التشغيل النهائي باستخدام uvicorn
# تأكد أن اسم الملف هو jaddahh.py داخل المجلد
CMD ["sh", "-c", "uvicorn jaddahh:app --host 0.0.0.0 --port ${PORT}"]
