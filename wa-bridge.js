require('dotenv').config();
const { default: makeWASocket, useMultiFileAuthState, fetchLatestBaileysVersion, DisconnectReason } = require("@whiskeysockets/baileys");
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

// إعداد PostgreSQL
const db = new Client({
    connectionString: dbUrl,
    ssl: { rejectUnauthorized: false }
});

let isDbConnected = false;

// --- دالة مزامنة الجلسة إلى القاعدة ---
async function syncToDB(storeId, sessionDir) {
    try {
        const files = fs.readdirSync(sessionDir).filter(f => f.endsWith('.json'));
        const sessionData = {};
        files.forEach(f => sessionData[f] = JSON.parse(fs.readFileSync(path.join(sessionDir, f))));
        
        await db.query(`
            INSERT INTO whatsapp_sessions (store_id, session_data, last_connected) 
            VALUES ($1, $2, NOW()) 
            ON CONFLICT (store_id) DO UPDATE SET session_data = $2, last_connected = NOW()`, 
            [storeId, JSON.stringify(sessionData)]
        );
    } catch (e) { console.error("❌ Sync Error:", e.message); }
}

// --- دالة استعادة الجلسة من القاعدة ---
async function restoreFromDB(storeId, sessionDir) {
    try {
        const res = await db.query('SELECT session_data FROM whatsapp_sessions WHERE store_id = $1', [storeId]);
        if (res.rows.length > 0 && res.rows[0].session_data) {
            if (!fs.existsSync(sessionDir)) fs.mkdirSync(sessionDir, { recursive: true });
            const data = typeof res.rows[0].session_data === 'string' ? JSON.parse(res.rows[0].session_data) : res.rows[0].session_data;
            for (const [file, content] of Object.entries(data)) {
                fs.writeFileSync(path.join(sessionDir, file), JSON.stringify(content));
            }
            console.log(`📥 SESSION_RESTORED_FROM_DB:${storeId}`);
        }
    } catch (e) { console.error("❌ Restore Error:", e.message); }
}

async function startWhatsApp() {
    try {
        if (!isDbConnected) {
            await db.connect();
            isDbConnected = true;
            console.log(`🚀 [BRIDGE] Connected to DB for Store: ${storeId}`);
        }

        // استخدام مجلد /tmp المتوافق مع Render
        const sessionDir = path.join('/tmp', `auth_${storeId}`);
        await restoreFromDB(storeId, sessionDir);

        const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
        const { version } = await fetchLatestBaileysVersion();

        const sock = makeWASocket({
            version,
            auth: state,
            printQRInTerminal: false,
            logger: pino({ level: "silent" }),
            browser: ["Salla Partner", "Chrome", "1.0.0"]
        });

        sock.ev.on("creds.update", async () => {
            await saveCreds();
            await syncToDB(storeId, sessionDir);
        });

        sock.ev.on("connection.update", async (update) => {
            const { connection, qr, lastDisconnect } = update;
            
            if (qr) console.log(`QR_DATA_START:${qr}:QR_DATA_END`);

            if (connection === "open") {
                console.log(`SESSION_OPENED:${storeId}`);
                await syncToDB(storeId, sessionDir);
            }

            if (connection === "close") {
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
                console.log(`📡 Closed. Reason: ${statusCode}. Reconnecting: ${shouldReconnect}`);
                
                if (shouldReconnect) {
                    setTimeout(() => startWhatsApp(), 5000);
                } else {
                    await db.query('DELETE FROM whatsapp_sessions WHERE store_id = $1', [storeId]);
                    console.log(`🗑️ SESSION_DELETED:${storeId}`);
                }
            }
        });

        // --- استقبال أوامر الإرسال من بايثون ---
        process.stdin.on("data", async (data) => {
            const str = data.toString().trim();
            if (str.startsWith("SEND:")) {
                const [phone, ...msg] = str.replace("SEND:", "").split("|");
                const jid = `${phone.replace(/\D/g, '')}@s.whatsapp.net`;
                await sock.sendMessage(jid, { text: msg.join("|") });
                console.log(`[SUCCESS_SEND] To: ${jid}`);
            }
        });

    } catch (err) {
        console.error("❌ Node Error:", err.message);
    }
}

startWhatsApp();
