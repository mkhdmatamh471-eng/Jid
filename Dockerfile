# استخدام النسخة الكاملة لتجنب مشاكل المترجمات والمكتبات المفقودة
FROM python:3.10

# إعدادات البيئة
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV NODE_ENV production

# تثبيت Node.js (النسخة الكاملة توفر أدوات البناء تلقائياً)
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# نسخ ملفات التبعيات
COPY package*.json ./

# تثبيت مكتبات Node
# استخدام --no-scripts لتجنب تشغيل أي عمليات بناء جانبية قد تسبب الفشل
RUN npm install --production --no-audit --no-fund

# تثبيت مكتبات بايثون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ الكود بالكامل
COPY . .

# المنفذ الخاص بـ Render
EXPOSE 10000

CMD ["python", "jaddahh.py"]
