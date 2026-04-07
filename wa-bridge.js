const { 
    default: makeWASocket, 
    DisconnectReason, 
    initAuthCreds, 
    BufferJSON, 
    proto,
    fetchLatestBaileysVersion 
} = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const pino = require("pino");
const { Pool } = require("pg"); // تم التغيير من Client إلى Pool

const storeId = process.argv[2] || "default";
const phoneNumber = process.argv[3];

console.log(`[START] 🚀 بدء تشغيل الجسر الذري للمتجر: ${storeId}`);

/**
 * 1. إعداد الـ Pool (اتصال واحد مستدام)
 * الـ Pool يمنع تكرار فتح الاتصال في كل عملية query
 */
const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false },
    max: 1, // اتصال واحد فقط لكل عملية جسر
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 5000,
});

// متغير لمتابعة حالة الاتصال بالقاعدة مرة واحدة فقط في السجلات
let isDbConnected = false;

/**
 * 2. دالة إدارة الجلسة (منطق كود الاختبار مع تحسين الـ Pool)
 */
async function usePostgresAuthState(sessionId) {
    
    const writeData = async (data, id) => {
        try {
            const jsonStr = JSON.stringify(data, BufferJSON.replacer);
            await pool.query(
                "INSERT INTO whatsapp_sessions (id, data) VALUES ($1, $2) ON CONFLICT (id) DO UPDATE SET data = $2",
                [`${sessionId}_${id}`, jsonStr]
            );
        } catch (err) {
            console.error(`[DB_WRITE_ERR] ❌: ${err.message}`);
        }
    };

    const readData = async (id) => {
        try {
            const res = await pool.query("SELECT data FROM whatsapp_sessions WHERE id = $1", [`${sessionId}_${id}`]);
            if (!isDbConnected) {
                console.log(`[DB] ✅ متصل بـ Supabase.`);
                isDbConnected = true;
            }
            return res.rows.length > 0 ? JSON.parse(JSON.stringify(res.rows[0].data), BufferJSON.reviver) : null;
        } catch (err) {
            return null;
        }
    };

    const removeData = async (id) => {
        await pool.query("DELETE FROM whatsapp_sessions WHERE id = $1", [`${sessionId}_${id}`]);
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

/**
 * 3. المحرك الرئيسي
 */
async function connectToWhatsApp() {
    try {
        console.log(`[WA] 🛠️ تهيئة المقبس...`);
        const { state, saveCreds } = await usePostgresAuthState(storeId);
        
        // جلب النسخة لمرة واحدة
        const { version } = await fetchLatestBaileysVersion();

        const sock = makeWASocket({
            version,
            auth: state,
            logger: pino({ level: "silent" }),
            browser: ["Jaddahh Dev", "Chrome", "1.1.0"],
            printQRInTerminal: false,
            syncFullHistory: false,
            connectTimeoutMs: 60000, // مهلة أطول للاتصالات الضعيفة
        });

        // طلب كود الربط
        if (!sock.authState.creds.registered && phoneNumber) {
            console.log(`[PAIRING] 🔑 طلب كود للرقم: ${phoneNumber}`);
            setTimeout(async () => {
                try {
                    const code = await sock.requestPairingCode(phoneNumber.replace(/\D/g, ''));
                    console.log(`PAIRING_CODE_START:${code}:PAIRING_CODE_END`);
                } catch (err) {
                    console.error(`[PAIRING_ERROR] ❌: ${err.message}`);
                }
            }, 10000); // زيادة المهلة لضمان استقرار الاتصال بالقاعدة أولاً
        }

        sock.ev.on("creds.update", saveCreds);

        sock.ev.on("connection.update", (update) => {
            const { connection, lastDisconnect, qr } = update;

            if (qr) console.log(`QR_DATA_START:${qr}:QR_DATA_END`);

            if (connection === "close") {
                const statusCode = (lastDisconnect?.error instanceof Boom)?.output?.statusCode;
                if (statusCode === 401) {
                    console.log(`[LOGOUT] 🗑️ مسح الجلسة التالفة...`);
                    pool.query("DELETE FROM whatsapp_sessions WHERE id LIKE $1", [`${storeId}_%`]);
                } else if (statusCode !== DisconnectReason.loggedOut) {
                    console.log(`[RECONNECT] 🔄 إعادة المحاولة...`);
                    setTimeout(() => connectToWhatsApp(), 5000);
                }
            } else if (connection === "open") {
                console.log(`[WA_READY] 🎉 SESSION_OPENED`);
            }
        });

        // معالجة المدخلات من بايثون
        process.stdin.on("data", async (data) => {
            const input = data.toString().trim();
            if (input.startsWith("SEND:")) {
                try {
                    const [phone, ...msgArr] = input.substring(5).split("|");
                    await sock.sendMessage(`${phone}@s.whatsapp.net`, { text: msgArr.join("|") });
                    console.log(`SENT_CONFIRMATION:${phone}`);
                } catch (e) { console.error(`[SEND_ERR]: ${e.message}`); }
            }
        });

        // رصد الرسائل الواردة
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
        console.error(`[FATAL] 💥: ${err.message}`);
        process.exit(1);
    }
}

connectToWhatsApp();
