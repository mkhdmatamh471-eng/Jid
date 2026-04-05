const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, initAuthCreds, BufferJSON } = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const pino = require("pino");
const { Client } = require("pg");

const storeId = process.argv[2] || "default";

// إعداد الاتصال بقاعدة البيانات (يأخذ DATABASE_URL تلقائياً من Render)
const dbClient = new Client({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false } // مطلوب لـ Render/Supabase
});

/**
 * وظيفة مخصصة لإدارة حالة المصادقة داخل PostgreSQL بدلاً من الملفات
 */
async function usePostgresAuthState(storeId) {
    await dbClient.connect();

    // إنشاء الجدول إذا لم يكن موجوداً (لحفظ بيانات الجلسات)
    await dbClient.query(`
        CREATE TABLE IF NOT EXISTS whatsapp_sessions (
            store_id TEXT PRIMARY KEY,
            creds JSONB,
            keys JSONB
        );
    `);

    // محاولة جلب البيانات الموجودة
    const res = await dbClient.query("SELECT creds, keys FROM whatsapp_sessions WHERE store_id = $1", [storeId]);
    
    let creds = res.rows[0]?.creds ? JSON.parse(JSON.stringify(res.rows[0].creds), BufferJSON.reviver) : initAuthCreds();
    let keys = res.rows[0]?.keys ? JSON.parse(JSON.stringify(res.rows[0].keys), BufferJSON.reviver) : {};

    const saveCreds = async () => {
        const credsJSON = JSON.stringify(creds, BufferJSON.replacer);
        const keysJSON = JSON.stringify(keys, BufferJSON.replacer);
        
        await dbClient.query(`
            INSERT INTO whatsapp_sessions (store_id, creds, keys)
            VALUES ($1, $2, $3)
            ON CONFLICT (store_id) DO UPDATE SET creds = $2, keys = $3
        `, [storeId, credsJSON, keysJSON]);
    };

    return {
        state: {
            creds,
            keys: {
                get: (type, ids) => ids.reduce((dict, id) => {
                    const value = keys[type]?.[id];
                    if (value) dict[id] = value;
                    return dict;
                }, {}),
                set: (data) => {
                    for (const type in data) {
                        keys[type] = keys[type] || {};
                        Object.assign(keys[type], data[type]);
                    }
                    saveCreds();
                }
            }
        },
        saveCreds
    };
}

async function connectToWhatsApp() {
    // استخدام Postgres بدلاً من useMultiFileAuthState
    const { state, saveCreds } = await usePostgresAuthState(storeId);

    const sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        logger: pino({ level: "silent" }),
        browser: ["Salla AI Bot", "Chrome", "1.0.0"],
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", (update) => {
        const { connection, lastDisconnect, qr } = update;
        
        if (qr) {
            console.log(`QR_DATA_START:${qr}:QR_DATA_END`);
        }

        if (connection === "close") {
            const shouldReconnect = (lastDisconnect.error instanceof Boom)?.output?.statusCode !== DisconnectReason.loggedOut;
            if (shouldReconnect) connectToWhatsApp();
        } else if (connection === "open") {
            console.log("SESSION_OPENED");
        }
    });

    // استلام الأوامر من بايثون لرسائل الصادر
    process.stdin.on("data", async (data) => {
        const str = data.toString().trim();
        if (str.startsWith("SEND:")) {
            try {
                const [_, target, ...msgParts] = str.split(":");
                const [phone, message] = msgParts.join(":").split("|");
                await sock.sendMessage(`${phone}@s.whatsapp.net`, { text: message });
                console.log(`SENT_CONFIRMATION:${phone}`);
            } catch (e) {
                console.log(`SEND_ERROR:${e.message}`);
            }
        }
    });

    // معالجة رسائل الوارد
    sock.ev.on("messages.upsert", async (m) => {
        const msg = m.messages[0];
        if (!msg.key.fromMe && m.type === "notify") {
            const sender = msg.key.remoteJid.split("@")[0];
            const text = msg.message?.conversation || msg.message?.extendedTextMessage?.text;
            if (text) {
                console.log(`NEW_MSG|${sender}|${text}`);
            }
        }
    });
}

connectToWhatsApp().catch(err => console.error("CRITICAL_NODE_ERROR:", err));
