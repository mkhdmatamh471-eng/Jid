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
const { Client } = require("pg");

const storeId = process.argv[2] || "default";
const phoneNumber = process.argv[3];

console.log(`[START] 🚀 بدء تشغيل الجسر الذري للمتجر: ${storeId}`);

// استخدام الـ Pooler (المنفذ 6543) إذا توفر في DATABASE_URL لضمان استقرار العمليات المتزامنة
const dbClient = new Client({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false } 
});

/**
 * دالة إدارة الجلسة بنظام "الصفوف المنفصلة" - Atomic System
 */
async function useAtomicAuthState(storeId) {
    try {
        if (!dbClient._connected) await dbClient.connect();
        console.log(`[DB] ✅ متصل بنظام الأرشفة الذرية.`);
    } catch (e) {
        console.error(`[DB_ERROR] ❌ فشل الاتصال: ${e.message}`);
    }

    // دالة الكتابة (حفظ قطعة بيانات واحدة)
    const writeData = async (data, id) => {
        try {
            const jsonStr = JSON.stringify(data, BufferJSON.replacer);
            // المفتاح الفريد هو دمج storeId مع نوع البيانات (id)
            await dbClient.query(`
                INSERT INTO whatsapp_sessions (store_id, key_id, data) 
                VALUES ($1, $2, $3) 
                ON CONFLICT (store_id, key_id) DO UPDATE SET data = $3
            `, [storeId, id, jsonStr]);
        } catch (err) {
            console.error(`[DB_WRITE_ERR] ❌ فشل حفظ ${id}:`, err.message);
        }
    };

    // دالة القراءة
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

    // دالة الحذف
    const removeData = async (id) => {
        await dbClient.query(
            "DELETE FROM whatsapp_sessions WHERE store_id = $1 AND key_id = $2", 
            [storeId, id]
        );
    };

    // جلب بيانات الاعتماد الأساسية
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
        console.log(`[WA] 🛠️ تهيئة المقبس بالنسخة الأحدث...`);
        const { state, saveCreds } = await useAtomicAuthState(storeId);
        
        // جلب نسخة واتساب المدعومة حالياً لمنع الحظر أو التعليق
        const { version } = await fetchLatestBaileysVersion();

        const sock = makeWASocket({
            version,
            auth: state,
            printQRInTerminal: false,
            logger: pino({ level: "silent" }),
            browser: ["Jaddahh Bot", "Chrome", "1.1.0"],
            syncFullHistory: false, // لتقليل استهلاك الذاكرة في Render
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
            }
            if (connection === "close") {
                const statusCode = (lastDisconnect?.error instanceof Boom)?.output?.statusCode;
                if (statusCode !== DisconnectReason.loggedOut) {
                    console.log(`[RECONNECT] 🔄 إعادة المحاولة خلال 5 ثوانٍ...`);
                    setTimeout(() => connectToWhatsApp(), 5000);
                }
            } else if (connection === "open") {
                console.log(`[WA_READY] 🎉 SESSION_OPENED`);
            }
        });

        // استقبال أوامر الإرسال من Python
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

        // تمرير الرسائل الواردة لـ Python
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
        console.error(`[CRITICAL_ERROR] 💥 انهيار الجسر: ${err.message}`);
        process.exit(1); // إغلاق لإجبار النظام على البدء من نظيف
    }
}

connectToWhatsApp();
