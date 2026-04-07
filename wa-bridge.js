const { default: makeWASocket, DisconnectReason, initAuthCreds, BufferJSON, proto } = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const pino = require("pino");
const { Client } = require("pg");

const storeId = process.argv[2] || "default";

const dbClient = new Client({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false } 
});

/**
 * محرك إدارة الجلسة المطور لـ PostgreSQL
 */
async function usePostgresAuthState(storeId) {
    try {
        if (!dbClient._connected) await dbClient.connect();
    } catch (e) {
        console.error("DB_CONNECTION_ERROR:", e.message);
    }

    // إنشاء الجدول إذا لم يوجد
    await dbClient.query(`
        CREATE TABLE IF NOT EXISTS whatsapp_sessions (
            store_id TEXT PRIMARY KEY,
            creds TEXT,
            keys TEXT
        );
    `);

    // جلب البيانات الحالية
    const res = await dbClient.query("SELECT creds, keys FROM whatsapp_sessions WHERE store_id = $1", [storeId]);
    
    // تحويل البيانات من نص (JSON) إلى كائنات تدعم الـ Buffers
    let creds = res.rows[0]?.creds ? JSON.parse(res.rows[0].creds, BufferJSON.reviver) : initAuthCreds();
    let keys = res.rows[0]?.keys ? JSON.parse(res.rows[0].keys, BufferJSON.reviver) : {};

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
                get: (type, ids) => {
                    const data = {};
                    ids.forEach(id => {
                        let value = keys[type]?.[id];
                        if (value) {
                            if (type === 'app-state-sync-key') {
                                value = proto.Message.AppStateSyncKeyData.fromObject(value);
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
                    saveCreds(); // حفظ تلقائي عند تحديث المفاتيح
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
        logger: pino({ level: "error" }), // تقليل السجلات لعدم ملء مساحة الرام
        browser: ["Jaddahh Bot", "Chrome", "1.0.0"],
        syncFullHistory: false, // تعطيل مزامنة السجل الكامل لتوفير البيانات والرام
    });

    // تحديث الـ Creds عند الضرورة
    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) console.log(`QR_DATA_START:${qr}:QR_DATA_END`);

        if (connection === "close") {
            const statusCode = (lastDisconnect.error instanceof Boom)?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
            
            console.log(`CONNECTION_CLOSED: Reason ${statusCode}, Reconnecting: ${shouldReconnect}`);
            
            if (shouldReconnect) {
                setTimeout(() => connectToWhatsApp(), 5000); // تأخير بسيط قبل إعادة المحاولة
            } else {
                console.log("SESSION_TERMINATED: User logged out.");
            }
        } else if (connection === "open") {
            console.log("SESSION_OPENED");
        }
    });

    // استقبال الأوامر من Python (إرسال رسائل)
    process.stdin.on("data", async (data) => {
        const input = data.toString().trim();
        if (input.startsWith("SEND:")) {
            try {
                // التنسيق المتوقع SEND:رقم_الهاتف|نص_الرسالة
                const payload = input.substring(5);
                const [phone, ...messageParts] = payload.split("|");
                const message = messageParts.join("|");

                await sock.sendMessage(`${phone}@s.whatsapp.net`, { text: message });
                console.log(`SENT_CONFIRMATION:${phone}`);
            } catch (e) {
                console.error(`SEND_ERROR:${e.message}`);
            }
        }
    });

    // مراقبة الرسائل الواردة وإرسالها لـ Python
    sock.ev.on("messages.upsert", async (m) => {
        if (m.type !== "notify") return;
        
        for (const msg of m.messages) {
            if (!msg.key.fromMe && msg.message) {
                const sender = msg.key.remoteJid.split("@")[0];
                const text = msg.message.conversation || 
                             msg.message.extendedTextMessage?.text || 
                             msg.message.buttonsResponseMessage?.selectedButtonId;

                if (text) {
                    // إرسال النص لـ Python للمعالجة عبر الذكاء الاصطناعي
                    console.log(`NEW_MSG|${sender}|${text}`);
                }
            }
        }
    });
}

// تشغيل البوت مع معالجة الأخطاء القاتلة
connectToWhatsApp().catch(err => {
    console.error("CRITICAL_BRIDGE_ERROR:", err);
});
