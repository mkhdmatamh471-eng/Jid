FROM python:3.10-slim

# إعدادات البيئة
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# تثبيت مكتبات النظام الضرورية
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# تثبيت التبعيات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ الكود
COPY . .

# التعديل المنقذ هنا:
# حذفنا الأقواس المربعة للسماح لـ Render بتمرير قيمة $PORT الحقيقية للسيرفر
CMD uvicorn jaddahh:app --host 0.0.0.0 --port $PORT
