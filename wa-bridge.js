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

console.log(`[START] 🚀 بدء تشغيل الجسر الذري للمتجر: ${storeId}`);

const dbClient = new Client({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false } 
});

async function useAtomicAuthState(storeId) {
    try {
        if (!dbClient._connected) await dbClient.connect();
        console.log(`[DB] ✅ متصل بنظام الأرشفة الذرية.`);
    } catch (e) {
        console.error(`[DB_ERROR] ❌ فشل الاتصال: ${e.message}`);
    }

    const writeData = async (data, id) => {
        try {
            const jsonStr = JSON.stringify(data, BufferJSON.replacer);
            await dbClient.query(`
                INSERT INTO whatsapp_sessions (store_id, key_id, data) 
                VALUES ($1, $2, $3) 
                ON CONFLICT (store_id, key_id) DO UPDATE SET data = $3
            `, [storeId, id, jsonStr]);
        } catch (err) {
            console.error(`[DB_WRITE_ERR] ❌ فشل حفظ ${id}:`, err.message);
        }
    };

    const readData = async (id) => {
        try {
            const res = await dbClient.query(
                "SELECT data FROM whatsapp_sessions WHERE store_id = $1 AND key_id = $2", 
                [storeId, id]
            );
            return res.rows.length > 0 ? JSON.parse(JSON.stringify(res.rows[0].data), BufferJSON.reviver) : null;
        } catch (err) {
            return null;
        }
    };

    const removeData = async (id) => {
        await dbClient.query("DELETE FROM whatsapp_sessions WHERE store_id = $1 AND key_id = $2", [storeId, id]);
    };

    const creds = await readData('creds') || initAuthCreds();

    return {
        state: {
            creds,
            keys: {
                get: async (type, ids) => {
                    const data = {};
                    await Promise.all(ids.map(async (id) => {
                        let value = await readData(`${type}-${id}`);
                        if (type === 'app-state-sync-key' && value) {
                            value = proto.Message.AppStateSyncKeyData.fromObject(value);
                        }
                        data[id] = value;
                    }));
                    return data;
                },
                set: async (data) => {
                    for (const type in data) {
                        for (const id in data[type]) {
                            const value = data[type][id];
                            value ? await writeData(value, `${type}-${id}`) : await removeData(`${type}-${id}`);
                        }
                    }
                }
            }
        },
        saveCreds: () => writeData(creds, 'creds')
    };
}

async function connectToWhatsApp() {
    try {
        console.log(`[WA] 🛠️ تهيئة المقبس (Atomic Base)...`);
        const { state, saveCreds } = await useAtomicAuthState(storeId);
        
        const sock = makeWASocket({
            // نسخة ثابتة ومستقرة جداً لتجنب مشاكل الجلب الخارجي
            version: [2, 3000, 1015901307],
            auth: state,
            printQRInTerminal: false,
            logger: pino({ level: "silent" }),
            browser: ["Ubuntu", "Chrome", "20.0.04"],
            // خيارات تحسين الأداء للسيرفرات الضعيفة
            syncFullHistory: false,
            markOnlineOnConnect: true,
            connectTimeoutMs: 60000,
            defaultQueryTimeoutMs: 0,
            generateHighQualityLinkPreview: false
        });

        if (!sock.authState.creds.registered && phoneNumber) {
            console.log(`[PAIRING] 🔑 طلب كود للرقم: ${phoneNumber}`);
            setTimeout(async () => {
                try {
                    const code = await sock.requestPairingCode(phoneNumber.replace(/\D/g, ''));
                    console.log(`PAIRING_CODE_START:${code}:PAIRING_CODE_END`);
                } catch (err) {
                    console.error(`[PAIRING_ERROR] ❌: ${err.message}`);
                }
            }, 8000); // زيادة التأخير لضمان جاهزية المقبس
        }

        sock.ev.on("creds.update", saveCreds);

        sock.ev.on("connection.update", (update) => {
            const { connection, lastDisconnect, qr } = update;
            if (qr) {
                console.log(`QR_DATA_START:${qr}:QR_DATA_END`);
                console.log(`[QR] ✅ تم توليد الكود.`);
            }
            if (connection === "close") {
                const statusCode = (lastDisconnect?.error instanceof Boom)?.output?.statusCode;
                console.log(`[WA_CLOSED] الحالة: ${statusCode}`);
                if (statusCode !== DisconnectReason.loggedOut) {
                    console.log(`[RECONNECT] 🔄 إعادة المحاولة...`);
                    setTimeout(() => connectToWhatsApp(), 5000);
                }
            } else if (connection === "open") {
                console.log(`[WA_READY] 🎉 SESSION_OPENED`);
            }
        });

        // المستمعين للأوامر والرسائل
        process.stdin.on("data", async (data) => {
            const input = data.toString().trim();
            if (input.startsWith("SEND:")) {
                try {
                    const [phone, ...msgArr] = input.substring(5).split("|");
                    await sock.sendMessage(`${phone}@s.whatsapp.net`, { text: msgArr.join("|") });
                    console.log(`SENT_CONFIRMATION:${phone}`);
                } catch (e) { console.error(`[SEND_ERROR] ❌: ${e.message}`); }
            }
        });

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
        // أهم سطر في الكود: سيخبرنا لماذا ينهار السكريبت
        console.error(`[FATAL_ERROR] 💥 انهيار كامل:`, err.message);
        console.error(err.stack);
        process.exit(1); 
    }
}

connectToWhatsApp();
