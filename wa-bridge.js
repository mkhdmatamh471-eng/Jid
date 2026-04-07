const { 
    default: makeWASocket, 
    DisconnectReason, 
    initAuthCreds, 
    BufferJSON, 
    proto 
} = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const pino = require("pino");
const { Client } = require("pg");

const storeId = process.argv[2] || "default";
const phoneNumber = process.argv[3];

console.log(`[START] 🚀 بدء تشغيل الجسر للمتجر: ${storeId}`);

const dbClient = new Client({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false } 
});

async function usePostgresAuthState(storeId) {
    console.log(`[DB] 🔄 محاولة الاتصال بقاعدة البيانات...`);
    try {
        if (!dbClient._connected) await dbClient.connect();
        console.log(`[DB] ✅ متصل.`);
    } catch (e) {
        console.error(`[DB_ERROR] ❌ فشل الاتصال: ${e.message}`);
    }

    const res = await dbClient.query("SELECT creds, keys FROM whatsapp_sessions WHERE store_id = $1", [storeId]);
    
    let creds = res.rows[0]?.creds ? JSON.parse(res.rows[0].creds, BufferJSON.reviver) : initAuthCreds();
    let keys = res.rows[0]?.keys ? JSON.parse(res.rows[0].keys, BufferJSON.reviver) : {};

    const saveCreds = async () => {
        try {
            const credsJSON = JSON.stringify(creds, BufferJSON.replacer);
            const keysJSON = JSON.stringify(keys, BufferJSON.replacer);
            await dbClient.query(`
                INSERT INTO whatsapp_sessions (store_id, creds, keys)
                VALUES ($1, $2, $3)
                ON CONFLICT (store_id) DO UPDATE SET creds = $2, keys = $3
            `, [storeId, credsJSON, keysJSON]);
        } catch (err) {
            console.error(`[SAVE_ERROR] ❌ فشل الحفظ: ${err.message}`);
        }
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
                            if (type === 'app-state-sync-key') value = proto.Message.AppStateSyncKeyData.fromObject(value);
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
    try {
        console.log(`[WA] 🛠️ تهيئة المقبس...`);
        const { state, saveCreds } = await usePostgresAuthState(storeId);

        const sock = makeWASocket({
            auth: state,
            printQRInTerminal: false,
            logger: pino({ level: "silent" }),
            browser: ["Jaddahh", "Chrome", "1.0.0"],
            syncFullHistory: false,
        });

        // دعم كود الربط
        if (!sock.authState.creds.registered && phoneNumber) {
            console.log(`[PAIRING] 🔑 طلب كود للرقم: ${phoneNumber}`);
            setTimeout(async () => {
                try {
                    const code = await sock.requestPairingCode(phoneNumber.replace(/\D/g, ''));
                    console.log(`PAIRING_CODE_START:${code}:PAIRING_CODE_END`);
                } catch (err) {
                    console.error(`[PAIRING_ERROR] ❌: ${err.message}`);
                }
            }, 5000);
        }

        sock.ev.on("creds.update", saveCreds);

        sock.ev.on("connection.update", (update) => {
            const { connection, lastDisconnect, qr } = update;
            if (qr) {
                console.log(`QR_DATA_START:${qr}:QR_DATA_END`);
                console.log(`[QR] ✅ تم توليد الباركود.`);
            }
            if (connection === "close") {
                const statusCode = (lastDisconnect?.error instanceof Boom)?.output?.statusCode;
                if (statusCode !== DisconnectReason.loggedOut) {
                    console.log(`[RECONNECT] 🔄 إعادة الاتصال...`);
                    setTimeout(() => connectToWhatsApp(), 5000);
                }
            } else if (connection === "open") {
                console.log(`[WA_READY] 🎉 الجلسة نشطة!`);
                console.log(`SESSION_OPENED`);
            }
        });

        // معالجة الأوامر من Python (إرسال الرسائل)
        process.stdin.on("data", async (data) => {
            const input = data.toString().trim();
            if (input.startsWith("SEND:")) {
                try {
                    const [phone, ...msgArr] = input.substring(5).split("|");
                    await sock.sendMessage(`${phone}@s.whatsapp.net`, { text: msgArr.join("|") });
                    console.log(`SENT_CONFIRMATION:${phone}`);
                } catch (e) {
                    console.error(`[SEND_ERROR] ❌: ${e.message}`);
                }
            }
        });

        // استقبال الرسائل
        sock.ev.on("messages.upsert", async (m) => {
            if (m.type !== "notify") return;
            for (const msg of m.messages) {
                if (!msg.key.fromMe && msg.message) {
                    const sender = msg.key.remoteJid.split("@")[0];
                    const text = msg.message.conversation || msg.message.extendedTextMessage?.text;
                    if (text) console.log(`NEW_MSG|${sender}|${text}`);
                }
            }
        });

    } catch (err) {
        console.error(`[CRITICAL_ERROR] 💥: ${err.message}`);
    }
}

connectToWhatsApp().catch(err => console.error(err));
