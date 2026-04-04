# 1. القاعدة الأساسية
FROM python:3.10-slim

# 2. مجلد العمل
WORKDIR /app

# 3. تثبيت تبعات النظام الأساسية (مهم جداً لـ psycopg2 و التشفير و Node.js)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    python3-dev \
    gcc \
    && curl -sL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 4. نسخ ملفات المتطلبات
COPY requirements.txt package.json ./

# 5. تحديث pip وتثبيت المكتبات (هنا تم حل المشكلة)
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && npm install --production

# 6. نسخ بقية الملفات
COPY . .

# 7. الإعدادات والتشغيل
ENV PORT=10000
ENV PYTHONUNBUFFERED=1
RUN mkdir -p /app/sessions && chmod 777 /app/sessions

EXPOSE 10000

CMD ["sh", "-c", "uvicorn jaddahh:app --host 0.0.0.0 --port ${PORT}"]
