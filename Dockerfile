FROM python:3.10-slim

# إعدادات البيئة
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# تثبيت مكتبات النظام الضرورية
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# تثبيت مكتبات بايثون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ كود المشروع بالكامل
COPY . .

# المنفذ الخاص بـ Render (تلقائياً يكون 10000 أو كما تحدده)
EXPOSE 10000

CMD ["python", "jaddahh.py"]
