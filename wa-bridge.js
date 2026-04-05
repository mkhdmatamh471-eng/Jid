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

// رقم الهاتف الذي زودتني به (بدون علامة +)
const phoneNumber = "967785022014"; 

const db = new Client({
    connectionString: dbUrl,
    ssl: { rejectUnauthorized: false }
});

let isDbConnected = false;

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
    } catch (e) { console.error("❌ Sync Error:", e.message); }
}

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
            return true;
        }
    } catch (e) { console.error("❌ Restore Error:", e.message); }
    return false;
}

async function startWhatsApp() {
    try {
        if (!isDbConnected) {
            await db.connect();
            isDbConnected = true;
            console.log(`🚀 [BRIDGE] Starting for Store: ${storeId}`);
        }

        const sessionDir = path.join('/tmp', `auth_${storeId}`);
        const hasSession = await restoreFromDB(storeId, sessionDir);

        const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
        const { version } = await fetchLatestBaileysVersion();

        const sock = makeWASocket({
            version,
            auth: state,
            printQRInTerminal: false,
            logger: pino({ level: "silent" }),
            browser: ["Ubuntu", "Chrome", "20.0.04"]
        });

        // طلب كود الربط إذا لم تكن هناك جلسة سابقة
        if (!sock.authState.creds.registered && !hasSession) {
            console.log(`⏳ جاري طلب كود الربط للرقم: ${phoneNumber}...`);
            setTimeout(async () => {
                try {
                    const code = await sock.requestPairingCode(phoneNumber);
                    console.log(`\n************************************`);
                    console.log(`🔑 YOUR PAIRING CODE: ${code}`);
                    console.log(`************************************\n`);
                } catch (err) {
                    console.error("❌ خطأ في طلب الكود:", err.message);
                }
            }, 10000); // تأخير 10 ثوانٍ لضمان استقرار الاتصال
        }

        sock.ev.on("creds.update", async () => {
            await saveCreds();
            await syncToDB(storeId, sessionDir);
        });

        sock.ev.on("connection.update", async (update) => {
            const { connection, lastDisconnect } = update;
            if (connection === "open") {
                console.log(`✅ SESSION_OPENED:${storeId}`);
                await syncToDB(storeId, sessionDir);
            }
            if (connection === "close") {
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                if (statusCode !== DisconnectReason.loggedOut) {
                    setTimeout(() => startWhatsApp(), 5000);
                }
            }
        });

    } catch (err) {
        console.error("❌ Node Error:", err.message);
        setTimeout(() => startWhatsApp(), 5000);
    }
}

startWhatsApp();
