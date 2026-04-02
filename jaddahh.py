import os
import hmac
import hashlib
import tarfile
import qrcode
import shutil
import base64
import json
import logging
import asyncio
import random
import tempfile
import io
from io import BytesIO
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from urllib.parse import quote

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from playwright.async_api import async_playwright
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

# --- 1. الإعدادات والتحميل ---
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jaddahh")

app = FastAPI(title="Salla AI Integrated Bot")
templates = Jinja2Templates(directory=".")

# مسار الجلسات المحلي (Render Disk)
SESSION_PATH = os.path.join(os.getcwd(), "whatsapp_sessions")
os.makedirs(SESSION_PATH, exist_ok=True)

# قاعدة البيانات
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# متغيرات المتصفح العالمية
playwright_manager = None
contexts: Dict[str, any] = {}
pages: Dict[str, any] = {}
memory_semaphore = asyncio.Semaphore(1) # حماية الرام في Render (متصفح واحد فقط للربط في نفس الوقت)
message_queue = asyncio.Queue()

# --- 2. وظائف قاعدة البيانات المساعدة ---
def execute_db_query(query: str, params: dict = None, fetch: str = None):
    try:
        with engine.connect() as connection:
            with connection.begin():
                result = connection.execute(text(query), params or {})
                if fetch == "one": return result.fetchone()
                if fetch == "all": return result.fetchall()
                return result
    except Exception as e:
        logger.error(f"❌ Database Error: {e}")
        raise e

# --- 3. محرك المتصفح والجلسات (Playwright) ---
async def cleanup_store_resources(store_id: str):
    try:
        if store_id in contexts:
            await contexts[store_id].close()
        pages.pop(store_id, None)
        contexts.pop(store_id, None)
        logger.info(f"♻️ تم تحرير ذاكرة المتجر {store_id}")
    except Exception as e:
        logger.error(f"❌ Error cleaning resources: {e}")

async def get_handler_for_store(store_id: str):
    global playwright_manager
    if store_id in pages and not pages[store_id].is_closed():
        return pages[store_id]

    async with memory_semaphore:
        try:
            if playwright_manager is None:
                playwright_manager = await async_playwright().start()

            store_path = os.path.join(SESSION_PATH, f"session_{store_id}")
            os.makedirs(store_path, exist_ok=True)
            
            # محاولة استعادة الجلسة من PostgreSQL إذا كان المجلد المحلي فارغاً
            if not os.listdir(store_path):
                await load_session_from_db(store_id)

            context = await playwright_manager.chromium.launch_persistent_context(
                user_data_dir=store_path,
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--single-process"],
                viewport={'width': 800, 'height': 600}
            )
            
            page = context.pages[0] if context.pages else await context.new_page()
            page.set_default_navigation_timeout(60000)
            
            if "web.whatsapp.com" not in page.url:
                await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")
            
            pages[store_id] = page
            contexts[store_id] = context
            return page
        except Exception as e:
            logger.error(f"❌ Playwright Launch Error ({store_id}): {e}")
            await cleanup_store_resources(store_id)
            return None

async def save_session_to_db(store_id: str):
    try:
        path = os.path.join(SESSION_PATH, f"session_{store_id}")
        if not os.path.exists(path): return
        
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for item in os.listdir(path):
                tar.add(os.path.join(path, item), arcname=item)
        
        b64_data = base64.b64encode(buffer.getvalue()).decode()
        query = """
            INSERT INTO store_sessions (store_id, session_data, updated_at)
            VALUES (:sid, :data, NOW())
            ON CONFLICT (store_id) DO UPDATE SET session_data = EXCLUDED.session_data, updated_at = NOW()
        """
        execute_db_query(query, {"sid": store_id, "data": b64_data})
    except Exception as e:
        logger.error(f"❌ Session Save Error: {e}")

async def load_session_from_db(store_id: str):
    row = execute_db_query("SELECT session_data FROM store_sessions WHERE store_id = :sid", {"sid": store_id}, "one")
    if row and row[0]:
        store_path = os.path.join(SESSION_PATH, f"session_{store_id}")
        os.makedirs(store_path, exist_ok=True)
        buffer = io.BytesIO(base64.b64decode(row[0]))
        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            tar.extractall(path=store_path)
        return True
    return False

# --- 4. خدمات سلة والذكاء الاصطناعي ---
async def salla_request(method: str, endpoint: str, store_id: str, payload: dict = None):
    row = execute_db_query("SELECT access_token FROM store_settings WHERE store_id = :sid", {"sid": store_id}, "one")
    if not row: return None
    
    headers = {"Authorization": f"Bearer {row[0]}", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"https://api.salla.dev/admin/v2/{endpoint.lstrip('/')}"
        resp = await client.request(method, url, headers=headers, json=payload)
        if resp.status_code == 401: # تجديد التوكن
            new_token = await refresh_salla_token(store_id)
            if new_token:
                headers["Authorization"] = f"Bearer {new_token}"
                resp = await client.request(method, url, headers=headers, json=payload)
        return resp.json() if resp.status_code in [200, 201] else None

async def refresh_salla_token(store_id: str):
    row = execute_db_query("SELECT refresh_token FROM store_settings WHERE store_id = :sid", {"sid": store_id}, "one")
    if not row: return None
    
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://accounts.salla.sa/oauth2/token", data={
            "client_id": os.getenv("SALLA_CLIENT_ID"),
            "client_secret": os.getenv("SALLA_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": row[0]
        })
        if resp.status_code == 200:
            data = resp.json()
            execute_db_query("UPDATE store_settings SET access_token=:a, refresh_token=:r WHERE store_id=:s", 
                             {"a": data["access_token"], "r": data["refresh_token"], "s": store_id})
            return data["access_token"]
    return None

async def groq_analyze_intent(message: str) -> dict:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", 
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                json={
                    "model": "llama3-70b-8192",
                    "messages": [{"role": "system", "content": "Return JSON: {is_order:bool, order_id:string, is_product:bool, product_name:string}"}, 
                                 {"role": "user", "content": message}],
                    "response_format": {"type": "json_object"}
                })
            return json.loads(resp.json()["choices"][0]["message"]["content"])
        except:
            return {"is_order": False, "order_id": None, "is_product": False, "product_name": None}

# --- 5. العمال والمهام الخلفية (Workers) ---
async def message_worker():
    while True:
        store_id, phone, text = await message_queue.get()
        try:
            page = await get_handler_for_store(store_id)
            if page:
                clean_phone = phone.replace("+", "").replace(" ", "")
                url = f"https://web.whatsapp.com/send?phone={clean_phone}&text={quote(text)}"
                await page.goto(url)
                await page.wait_for_selector('div[contenteditable="true"][data-tab="10"]', timeout=30000)
                await asyncio.sleep(1)
                await page.keyboard.press("Enter")
                logger.info(f"✅ Sent to {phone}")
        except Exception as e:
            logger.error(f"❌ Worker Error: {e}")
        finally:
            message_queue.task_done()
            await asyncio.sleep(random.uniform(2, 5))

# --- 6. نقاط النهاية (API Endpoints) ---
@app.on_event("startup")
async def startup():
    asyncio.create_task(message_worker())
    logger.info("🚀 Bot Services Started")

@app.get("/admin/get-qr/{store_id}")
async def get_qr(store_id: str):
    page = await get_handler_for_store(store_id)
    if not page: return {"status": "error", "message": "Failed to open browser"}
    
    try:
        # فحص الحالة
        is_connected = await page.query_selector("div[data-testid='chat-list']")
        if is_connected: return {"status": "connected"}

        await page.wait_for_selector("canvas", timeout=30000)
        canvas = await page.query_selector("canvas")
        img_bytes = await canvas.screenshot()
        img_b64 = base64.b64encode(img_bytes).decode()
        
        # مراقبة النجاح في الخلفية
        asyncio.create_task(monitor_connection(page, store_id))
        
        return {"status": "ready", "qr_code": f"data:image/png;base64,{img_b64}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

async def monitor_connection(page, store_id):
    try:
        await page.wait_for_selector("div[data-testid='chat-list']", timeout=300000)
        await save_session_to_db(store_id)
        logger.info(f"✅ Store {store_id} Connected Successfully")
    except:
        pass

@app.get("/admin/dashboard/{store_id}", response_class=HTMLResponse)
async def dashboard(request: Request, store_id: str):
    return templates.TemplateResponse("index.html", {"request": request, "store_id": store_id})

@app.get("/api/dashboard/{store_id}")
async def api_dashboard(store_id: str):
    # جلب إحصائيات سريعة من القاعدة
    convs = execute_db_query("SELECT COUNT(*) FROM conversations", fetch="one")[0]
    revenue = execute_db_query("SELECT SUM(recovered_amount) FROM reminders_log WHERE store_id=:s", {"s": store_id}, "one")[0] or 0
    return {
        "summary": {"total_revenue_saved": float(revenue)},
        "bot_usage": convs,
        "browser_connected": store_id in pages
    }

@app.post("/webhook/salla")
async def salla_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    event = data.get("event")
    store_id = str(data.get("merchant"))
    
    if event == "chat.message.created" and data["data"]["type"] == "sent_by_customer":
        phone = data["data"]["customer"]["mobile"]
        text = data["data"]["message"]
        # هنا تضع منطق الرد باستخدام Groq ووضعه في message_queue
        # background_tasks.add_task(process_ai_reply, store_id, phone, text)
        
    return {"status": "ok"}

@app.get("/")
async def root():
    return RedirectResponse("/admin/dashboard/1867788552")
