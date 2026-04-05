FROM python:3.10-slim

# تثبيت Node.js وتبعات النظام
RUN apt-get update && apt-get install -y \
    curl gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean

WORKDIR /app

# تثبيت مكتبات Node
COPY package.json .
RUN npm install

# تثبيت مكتبات Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ بقية الملفات
COPY . .

# إنشاء مجلد الجلسات
RUN mkdir -p whatsapp_sessions

# تشغيل التطبيق
CMD ["python", "jaddahh.py"]
