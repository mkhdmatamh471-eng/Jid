FROM python:3.10-slim

# إعدادات البيئة
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# تأكد من أن المنفذ معرف كمتغير بيئة ليقرأه uvicorn
ENV PORT=10000 

WORKDIR /app

# تثبيت مكتبات النظام الضرورية (خفيفة جداً)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# تثبيت التبعيات (سيتم تخزينها في الـ Cache لتسريع الديبلوي القادم)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ الكود
COPY . .

# المنفذ
EXPOSE 10000

# التعديل الجوهري هنا:
# نستخدم uvicorn مباشرة للتأكد من ربط السيرفر بـ 0.0.0.0 ليكون متاحاً للإنترنت
CMD ["uvicorn", "jaddahh:app", "--host", "0.0.0.0", "--port", "10000"]
