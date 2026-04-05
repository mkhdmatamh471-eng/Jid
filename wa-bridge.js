require('dotenv').config();
const { 
    default: makeWASocket, 
    useMultiFileAuthState, 
    fetchLatestBaileysVersion, 
    DisconnectReason 
} = require("@whiskeysockets/baileys");
const pino = require("pino");
const fs = require('fs');
const path = require('path');
const { Client } = require('pg');

const storeId = process.argv[2];
const dbUrl = process.env.DATABASE_URL;

if (!storeId || !dbUrl) {
    console.error("❌ Missing StoreID or DATABASE_URL");
    process.exit(1);
}

// إعداد اتصال PostgreSQL
const db = new Client({
    connectionString: dbUrl,
    ssl: dbUrl.includes('localhost') ? false : { rejectUnauthorized: false }
});

let isDbConnected = false;

// --- دالة مزامنة الجلسة إلى القاعدة ---
async function syncToDB(storeId, sessionDir) {
    try {
        if (!fs.existsSync(sessionDir)) return;
        const files = fs.readdirSync(sessionDir).filter(f => f.endsWith('.json'));
        const sessionData = {};
        
        files.forEach(f => {
            sessionData[f] = JSON.parse(fs.readFileSync(path.join(sessionDir, f)));
        });

        await db.query(`
            INSERT INTO whatsapp_sessions (store_id, session_data, last_connected) 
            VALUES ($1, $2, NOW()) 
            ON CONFLICT (store_id) DO UPDATE SET session_data = $2, last_connected = NOW()`, 
            [storeId, JSON.stringify(sessionData)]
        );
    } catch (e) { 
        console.error("❌ Sync Error:", e.message); 
    }
}

// --- دالة استعادة الجلسة من القاعدة ---
async function restoreFromDB(storeId, sessionDir) {
    try {
        const res = await db.query('SELECT session_data FROM whatsapp_sessions WHERE store_id = $1', [storeId]);
        if (res.rows.length > 0 && res.rows[0].session_data) {
            if (!fs.existsSync(sessionDir)) fs.mkdirSync(sessionDir, { recursive: true });
            
            const data = typeof res.rows[0].session_data === 'string' 
                ? JSON.parse(res.rows[0].session_data) 
                : res.rows[0].session_data;

            for (const [file, content] of Object.entries(data)) {
                fs.writeFileSync(path.join(sessionDir, file), JSON.stringify(content));
            }
            console.log(`📥 SESSION_RESTORED_FROM_DB:${storeId}`);
        }
    } catch (e) { 
        console.error("❌ Restore Error:", e.message); 
    }
}

async function startWhatsApp() {
    try {
        // الاتصال بالقاعدة مرة واحدة فقط
        if (!isDbConnected) {
            await db.connect();
            isDbConnected = true;
            console.log(`🚀 [BRIDGE] Connected to DB for Store: ${storeId}`);
        }

        // استخدام مجلد /tmp المتوافق مع البيئات السحابية
        const sessionDir = path.join('/tmp', `auth_${storeId}`);
        await restoreFromDB(storeId, sessionDir);

        const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
        const { version } = await fetchLatestBaileysVersion();

        const sock = makeWASocket({
            version,
            auth: state,
            printQRInTerminal: false,
            logger: pino({ level: "silent" }),
            // هوية متصفح "ماك" لزيادة استقرار الاتصال في السيرفرات
            browser: ["Mac OS", "Chrome", "110.0.5481.177"],
            connectTimeoutMs: 60000,
            keepAliveIntervalMs: 15000,
            generateHighQualityLinkPreview: false
        });

        // مزامنة التغييرات فور حدوثها
        sock.ev.on("creds.update", async () => {
            await saveCreds();
            await syncToDB(storeId, sessionDir);
        });

        sock.ev.on("connection.update", async (update) => {
            const { connection, qr, lastDisconnect } = update;

            if (qr) {
                console.log(`QR_DATA_START:${qr}:QR_DATA_END`);
            }

            if (connection === "open") {
                console.log(`SESSION_OPENED:${storeId}`);
                await syncToDB(storeId, sessionDir);
            }

            if (connection === "close") {
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
                
                console.log(`📡 Closed. Reason: ${statusCode}. Reconnecting: ${shouldReconnect}`);

                if (shouldReconnect) {
                    // تأخير 5 ثوانٍ لمنع الـ Loop وحظر الـ IP
                    setTimeout(() => startWhatsApp(), 5000);
                } else {
                    await db.query('DELETE FROM whatsapp_sessions WHERE store_id = $1', [storeId]);
                    if (fs.existsSync(sessionDir)) fs.rmSync(sessionDir, { recursive: true, force: true });
                    console.log(`🗑️ SESSION_DELETED:${storeId}`);
                }
            }
        });

        // استقبال أوامر الإرسال من بايثون عبر stdin
        process.stdin.on("data", async (data) => {
            try {
                const str = data.toString().trim();
                if (str.startsWith("SEND:")) {
                    const parts = str.replace("SEND:", "").split("|");
                    if (parts.length < 2) return;
                    
                    const phone = parts[0].replace(/\D/g, '');
                    const message = parts.slice(1).join("|");
                    const jid = `${phone}@s.whatsapp.net`;
                    
                    await sock.sendMessage(jid, { text: message });
                    console.log(`[SUCCESS_SEND] To: ${jid}`);
                }
            } catch (err) {
                console.error(`[SEND_ERROR] ${err.message}`);
            }
        });

    } catch (err) {
        console.error("❌ CRITICAL_NODE_ERROR:", err.message);
    }
}

// تشغيل البوت
startWhatsApp();
