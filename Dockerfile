# 1. القاعدة الأساسية
FROM python:3.10-slim

# 2. مجلد العمل
WORKDIR /app

# 3. تثبيت جميع التبعات (أضفنا git هنا)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    python3-dev \
    gcc \
    git \
    && curl -sL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 4. نسخ ملفات التعريف أولاً لسرعة البناء (Cache)
COPY requirements.txt package.json ./

# 5. تثبيت المكتبات (تأكد من تحديث pip و npm)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && npm install --production

# 6. نسخ بقية الملفات
COPY . .

# 7. إعداد المجلدات والمتغيرات
ENV PORT=10000
ENV PYTHONUNBUFFERED=1
RUN mkdir -p /app/sessions && chmod 777 /app/sessions

EXPOSE 10000

# 8. التشغيل
CMD ["sh", "-c", "uvicorn jaddahh:app --host 0.0.0.0 --port ${PORT}"]
