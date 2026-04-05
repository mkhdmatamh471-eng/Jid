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
const { Client } = require('pg'); // استخدام مكتبة pg مباشرة

// --- إعداد الاتصال بـ PostgreSQL ---
const dbConfig = {
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false } // مطلوب لاتصالات Render/Supabase
};

const db = new Client(dbConfig);
db.connect().catch(err => console.error("❌ DB_CONNECTION_ERROR:", err.message));

// --- دوال المزامنة مع PostgreSQL ---

/**
 * تحويل مجلد الجلسة إلى كائن JSON وتخزينه في القاعدة
 */
async function syncSessionToPostgres(storeId, sessionDir) {
    try {
        if (!fs.existsSync(sessionDir)) return;

        const files = fs.readdirSync(sessionDir);
        const sessionData = {};

        for (const file of files) {
            if (file.endsWith('.json')) {
                const filePath = path.join(sessionDir, file);
                const fileContent = fs.readFileSync(filePath, 'utf-8');
                sessionData[file] = JSON.parse(fileContent);
            }
        }

        const query = `
            INSERT INTO whatsapp_sessions (store_id, session_data, last_connected)
            VALUES ($1, $2, NOW())
            ON CONFLICT (store_id) DO UPDATE 
            SET session_data = EXCLUDED.session_data, last_connected = NOW();
        `;

        await db.query(query, [storeId, JSON.stringify(sessionData)]);
    } catch (error) {
        console.error(`❌ [SYNC_ERROR] ${error.message}`);
    }
}

/**
 * استعادة الملفات من قاعدة البيانات إلى مجلد /tmp
 */
async function restoreSessionFromPostgres(storeId, sessionDir) {
    try {
        const res = await db.query('SELECT session_data FROM whatsapp_sessions WHERE store_id = $1', [storeId]);
        
        if (res.rows.length > 0 && res.rows[0].session_data) {
            const sessionData = typeof res.rows[0].session_data === 'string' 
                ? JSON.parse(res.rows[0].session_data) 
                : res.rows[0].session_data;

            if (!fs.existsSync(sessionDir)) {
                fs.mkdirSync(sessionDir, { recursive: true });
            }

            for (const [filename, content] of Object.entries(sessionData)) {
                fs.writeFileSync(path.join(sessionDir, filename), JSON.stringify(content, null, 2));
            }
            console.log(`📥 SESSION_RESTORED_FROM_DB:${storeId}`);
        }
    } catch (error) {
        console.error(`❌ [RESTORE_ERROR] ${error.message}`);
    }
}

// --- الدالة الأساسية لتشغيل واتساب ---
async function startWhatsApp(storeId) {
    const sessionDir = path.join('/tmp', `auth_info_${storeId}`);
    
    // 1. استعادة الجلسة أولاً
    await restoreSessionFromPostgres(storeId, sessionDir);

    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
        version,
        auth: state,
        printQRInTerminal: false,
        logger: pino({ level: "silent" }),
        browser: ["Salla AI", "Chrome", "1.0.0"],
        syncFullHistory: false
    });

    // 2. تحديث الاعتمادات (مزامنة فورية)
    sock.ev.on("creds.update", async () => {
        await saveCreds();
        await syncSessionToPostgres(storeId, sessionDir);
    });

    sock.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log(`QR_DATA_START:${qr}:QR_DATA_END`);
        }

        if (connection === "close") {
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

            if (shouldReconnect) {
                startWhatsApp(storeId);
            } else {
                // حذف الجلسة من القاعدة إذا سجل المستخدم خروجاً يدوياً
                await db.query('DELETE FROM whatsapp_sessions WHERE store_id = $1', [storeId]);
                fs.rmSync(sessionDir, { recursive: true, force: true });
                console.log(`🗑️ SESSION_DELETED:${storeId}`);
            }
        } else if (connection === "open") {
            console.log(`SESSION_OPENED:${storeId}`);
            await syncSessionToPostgres(storeId, sessionDir);
        }
    });

    // --- استقبال أوامر الإرسال من بايثون ---
    process.stdin.on("data", async (data) => {
        try {
            const str = data.toString().trim();
            if (str.startsWith("SEND:")) {
                const [phone, ...msgParts] = str.replace("SEND:", "").split("|");
                const message = msgParts.join("|");
                const jid = phone.includes("@") ? phone : `${phone}@s.whatsapp.net`;
                
                await sock.sendMessage(jid, { text: message });
                console.log(`[SUCCESS_SEND] To: ${jid}`);
            }
        } catch (err) {
            console.error(`[SEND_ERROR] ${err.message}`);
        }
    });
}

// البدء
const storeId = process.argv[2];
if (storeId) {
    startWhatsApp(storeId).catch(err => console.error("CRITICAL_NODE_ERROR:", err));
}
