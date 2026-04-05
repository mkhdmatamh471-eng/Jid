# 1. القاعدة الأساسية
FROM python:3.10-slim

# 2. مجلد العمل
WORKDIR /app

# 3. تثبيت التبعات (تم إضافة مكتبات الوسائط والتشفير الضرورية لـ Baileys)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    python3-dev \
    gcc \
    git \
    ffmpeg \
    libnss3 \
    libatk-bridge2.0-0 \
    libxcomposite1 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && curl -sL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 4. نسخ ملفات التعريف لسرعة البناء
COPY requirements.txt package.json package-lock.json* ./

# 5. تثبيت المكتبات (بايثون ونود)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && npm install --production

# 6. نسخ بقية الملفات
COPY . .

# 7. إعداد البيئة والمجلدات المؤقتة
ENV PORT=10000
ENV PYTHONUNBUFFERED=1
# Render يحتاج لصلاحيات كاملة على المجلدات التي سيكتب فيها نود
RUN mkdir -p /tmp && chmod -R 777 /tmp

EXPOSE 10000

# 8. التشغيل
CMD ["sh", "-c", "uvicorn jaddahh:app --host 0.0.0.0 --port ${PORT}"]
