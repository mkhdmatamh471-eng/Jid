# 1. القاعدة الأساسية (نسخة نحيفة ومستقرة)
FROM python:3.10-slim

# 2. مجلد العمل
WORKDIR /app

# 3. تثبيت التبعات الأساسية للنظام (Python + Node.js)
# تم دمج العمليات لتقليل حجم الحاوية
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    python3-dev \
    gcc \
    git \
    && curl -sL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 4. نسخ ملفات التعريف أولاً للاستفادة من الـ Cache
COPY requirements.txt package.json package-lock.json* ./

# 5. تثبيت مكتبات بايثون ونود
# ملاحظة: سيقوم npm install بتثبيت 'pg' و 'dotenv' تلقائياً إذا كانت في package.json
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && npm install --production

# 6. نسخ بقية ملفات المشروع
COPY . .

# 7. إعداد متغيرات البيئة
# PORT سيتم استلامه تلقائياً من Render
ENV PORT=10000
ENV PYTHONUNBUFFERED=1

# التوافق مع مسار /tmp للجلسات (Render يمنح صلاحيات كاملة لـ /tmp)
RUN mkdir -p /tmp && chmod 777 /tmp

EXPOSE 10000

# 8. أمر التشغيل
# استخدمنا الاسم jaddahh:app بناءً على ملفك
CMD ["sh", "-c", "uvicorn jaddahh:app --host 0.0.0.0 --port ${PORT}"]
