# 1. استخدام نسخة بايثون كقاعدة أساسية
FROM python:3.10-slim

# 2. تعيين مجلد العمل
WORKDIR /app

# 3. تثبيت تبعات النظام (أضفنا curl لتثبيت Node.js)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && curl -sL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 4. نسخ ملفات المتطلبات للغتين (للاستفادة من الـ Cache)
COPY requirements.txt package.json ./

# 5. تثبيت مكتبات البايثون والنود
RUN pip install --no-cache-dir -r requirements.txt \
    && npm install --production

# 6. نسخ بقية ملفات المشروع
COPY . .

# 7. إعداد متغيرات البيئة
ENV PORT=10000
ENV PYTHONUNBUFFERED=1
# مهم لـ Baileys: التأكد من وجود مجلدات الجلسات بصلاحيات كتابة
RUN mkdir -p /app/sessions && chmod 777 /app/sessions

EXPOSE 10000

# 8. أمر التشغيل
# uvicorn سيعمل كالسابق، والبايثون هو من سيقوم بتشغيل Node.js كـ Subprocess
CMD ["sh", "-c", "uvicorn jaddahh:app --host 0.0.0.0 --port ${PORT}"]
