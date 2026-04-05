# استخدام صورة بايثون نحيفة كقاعدة أساسية
FROM python:3.10-slim

# منع بايثون من إنشاء ملفات .pyc وتفعيل التحديث الفوري للسجلات (Logs)
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# تثبيت Node.js وأدوات النظام الضرورية
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    build-essential \
    libpq-dev \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. تثبيت تبعات Node.js أولاً (للاستفادة من خاصية الـ Caching)
COPY package.json .
# تأكد من أن package.json يحتوي على "pg" و "@whiskeysockets/baileys"
RUN npm install --production

# 2. تثبيت تبعات Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. نسخ كود المشروع بالكامل
COPY . .

# ملاحظة: تم إزالة إنشاء مجلد whatsapp_sessions لأننا نعتمد الآن على PostgreSQL
# ولكن سنترك تصريح المنفذ (Port) كإجراء تنظيمي لـ Render
EXPOSE 10000

# تشغيل التطبيق الرئيسي
CMD ["python", "jaddahh.py"]
