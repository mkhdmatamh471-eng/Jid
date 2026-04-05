FROM python:3.10-slim

# إعدادات البيئة لتقليل استهلاك الذاكرة وتسريع التشغيل
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV NODE_ENV production

# تثبيت الأدوات اللازمة لبناء مكتبات Node (مهم جداً لـ pg و baileys)
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

# نسخ ملفات التبعيات
COPY package.json ./
# إذا كان لديك package-lock.json انسخه أيضاً، إن لم يوجد سيتخطاه الأمر
COPY package-lock.json* ./

# تثبيت مكتبات Node مع بارامترات لتقليل الضغط على السيرفر
# --no-audit و --no-fund يقللان من استهلاك الذاكرة أثناء البناء في Render
RUN npm install --production --no-audit --no-fund --loglevel=error

# تثبيت مكتبات بايثون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ كود المشروع
COPY . .

# المنفذ الافتراضي لـ Render
EXPOSE 10000

CMD ["python", "jaddahh.py"]
