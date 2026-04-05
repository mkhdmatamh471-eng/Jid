const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, initAuthCreds, BufferJSON } = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const pino = require("pino");
const { Client } = require("pg");

const storeId = process.argv[2] || "default";

// إعداد الاتصال بقاعدة البيانات
const dbClient = new Client({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false } 
});

/**
 * دالة متقدمة لإدارة الجلسة عبر PostgreSQL مع دعم كامل للـ Binary Data
 */
async function usePostgresAuthState(storeId) {
    try {
        if (!dbClient._connected) await dbClient.connect();
    } catch (e) {
        console.error("DATABASE_CONNECTION_ERROR:", e.message);
    }

    // إنشاء الجدول وتفعيل JSONB لسرعة الاستعلام
    await dbClient.query(`
        CREATE TABLE IF NOT EXISTS whatsapp_sessions (
            store_id TEXT PRIMARY KEY,
            creds JSONB,
            keys JSONB
        );
    `);

    const res = await dbClient.query("SELECT creds, keys FROM whatsapp_sessions WHERE store_id = $1", [storeId]);
    
    // استخدام BufferJSON.reviver لتحويل النصوص إلى Buffers عند القراءة
    let creds = res.rows[0]?.creds ? JSON.parse(JSON.stringify(res.rows[0].creds), BufferJSON.reviver) : initAuthCreds();
    let keys = res.rows[0]?.keys ? JSON.parse(JSON.stringify(res.rows[0].keys), BufferJSON.reviver) : {};

    const saveCreds = async () => {
        // استخدام BufferJSON.replacer لتحويل الـ Buffers إلى نصوص عند الحفظ
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
                get: (type, ids) => {
                    const data = {};
                    ids.forEach(id => {
                        let value = keys[type]?.[id];
                        if (value) {
                            // إعادة بناء الـ Buffer إذا لزم الأمر
                            if (type === 'app-state-sync-key' && value) {
                                value = JSON.parse(JSON.stringify(value), BufferJSON.reviver);
                            }
                            data[id] = value;
                        }
                    });
                    return data;
                },
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
    const { state, saveCreds } = await usePostgresAuthState(storeId);

    const sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        logger: pino({ level: "silent" }),
        browser: ["Salla AI Bot", "Chrome", "1.0.0"],
        // تحسين لتقليل استهلاك الذاكرة في Render
        patchMessageBeforeSending: (message) => {
            const requiresPatch = !!(message.buttonsMessage || message.templateMessage || message.listMessage);
            if (requiresPatch) {
                message = { viewOnceMessage: { message: { messageContextInfo: { deviceListMetadataVersion: 2, deviceListMetadata: {}, }, ...message } } };
            }
            return message;
        }
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect, qr } = update;
        
        if (qr) console.log(`QR_DATA_START:${qr}:QR_DATA_END`);

        if (connection === "close") {
            const shouldReconnect = (lastDisconnect.error instanceof Boom)?.output?.statusCode !== DisconnectReason.loggedOut;
            if (shouldReconnect) {
                console.log("RECONNECTING...");
                connectToWhatsApp();
            }
        } else if (connection === "open") {
            console.log("SESSION_OPENED");
        }
    });

    // معالجة الأوامر من بايثون
    process.stdin.on("data", async (data) => {
        const str = data.toString().trim();
        if (str.startsWith("SEND:")) {
            try {
                const parts = str.split(":");
                const payload = parts.slice(2).join(":"); // لضمان عدم ضياع الرسالة لو بها ":"
                const [phone, message] = payload.split("|");
                await sock.sendMessage(`${phone}@s.whatsapp.net`, { text: message });
                console.log(`SENT_CONFIRMATION:${phone}`);
            } catch (e) {
                console.log(`SEND_ERROR:${e.message}`);
            }
        }
    });

    // معالجة الرسائل الواردة
    sock.ev.on("messages.upsert", async (m) => {
        const msg = m.messages[0];
        if (!msg.key.fromMe && m.type === "notify") {
            const sender = msg.key.remoteJid.split("@")[0];
            const text = msg.message?.conversation || msg.message?.extendedTextMessage?.text;
            if (text) console.log(`NEW_MSG|${sender}|${text}`);
        }
    });
}

connectToWhatsApp().catch(err => {
    console.error("CRITICAL_NODE_ERROR:", err.message);
});
