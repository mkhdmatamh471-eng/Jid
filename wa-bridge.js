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

// --- إعداد الاتصال بـ PostgreSQL ---
const db = new Client({
    connectionString: dbUrl,
    ssl: dbUrl.includes('localhost') ? false : { rejectUnauthorized: false }
});

let isDbConnected = false;

// --- دوال المزامنة مع PostgreSQL ---
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
    try {
        // الاتصال بالقاعدة مرة واحدة فقط
        if (!isDbConnected) {
            await db.connect();
            isDbConnected = true;
            console.log(`🚀 [BRIDGE] Connected to DB for Store: ${storeId}`);
        }

        const sessionDir = path.join('/tmp', `auth_info_${storeId}`);

        // 1. استعادة الجلسة
        await restoreSessionFromPostgres(storeId, sessionDir);

        const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
        const { version } = await fetchLatestBaileysVersion();

        const sock = makeWASocket({
            version,
            auth: state,
            printQRInTerminal: false,
            logger: pino({ level: "silent" }),
            browser: ["Salla Partner AI", "Chrome", "1.0.0"], // متصفح احترافي لتجنب الحظر
            syncFullHistory: false
        });

        // 2. تحديث الاعتمادات والمزامنة
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

                console.log(`📡 Connection closed. Reason: ${statusCode}. Reconnecting: ${shouldReconnect}`);

                if (shouldReconnect) {
                    // تأخير 5 ثوانٍ لمنع خطأ 405 (Loop)
                    setTimeout(() => startWhatsApp(storeId), 5000);
                } else {
                    // العميل سجل خروج من التطبيق
                    await db.query('DELETE FROM whatsapp_sessions WHERE store_id = $1', [storeId]);
                    if (fs.existsSync(sessionDir)) fs.rmSync(sessionDir, { recursive: true, force: true });
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

    } catch (err) {
        console.error("❌ CRITICAL_NODE_ERROR:", err.message);
    }
}

// البدء
if (storeId) {
    startWhatsApp(storeId);
}
