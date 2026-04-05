# استخدام صورة بايثون نحيفة
FROM python:3.10-slim

# إعدادات البيئة
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# تثبيت Node.js والتبعيات اللازمة للبناء
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    build-essential \
    libpq-dev \
    python3 \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# نسخ ملفات التبعيات أولاً
COPY package.json ./
# إذا كان لديك ملف package-lock.json انسخه أيضاً لضمان استقرار النسخ
COPY package-lock.json* ./

# محاولة التثبيت مع زيادة المهلة الزمنية وتجاهل الـ Scripts غير الضرورية
# واستخدام --no-audit لتوفير الذاكرة في Render
RUN npm install --production --no-audit --fund false || \
    (sleep 5 && npm install --production --no-audit --fund false)

# تثبيت مكتبات بايثون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ بقية الملفات
COPY . .

EXPOSE 10000

CMD ["python", "jaddahh.py"]
