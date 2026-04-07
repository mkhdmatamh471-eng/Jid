// DEBUG: أول سطر للتأكد من تشغيل الملف
console.log("DEBUG: Script started, checking DB connection...");

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

/**
 * إعداد قاعدة البيانات مع معالجة الأخطاء والـ SSL
 */
const dbClient = new Client({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false },
    connectionTimeoutMillis: 10000, // مهلة 10 ثوانٍ للاتصال
});

async function usePostgresAuthState(storeId) {
    try {
        console.log(`[DB] 🔄 محاولة الاتصال بـ Supabase...`);
        await dbClient.connect();
        console.log(`[DB] ✅ تم الاتصال بنجاح.`);

        console.log(`[DB] 🔍 استعلام بيانات المتجر: ${storeId}`);
        // إضافة Timeout للاستعلام لكي لا يظل معلقاً للأبد
        const res = await dbClient.query({
            text: "SELECT creds, keys FROM whatsapp_sessions WHERE store_id = $1",
            values: [storeId],
            rowMode: 'array' // لضمان سرعة الاستجابة
        });

        console.log(`[DB] ✅ اكتمل الاستعلام. عدد النتائج: ${res.rowCount}`);

        // معالجة البيانات بأمان (Try/Catch للـ JSON)
        let creds, keys;
        try {
            const row = res.rows[0];
            creds = row && row[0] ? JSON.parse(row[0], BufferJSON.reviver) : initAuthCreds();
            keys = row && row[1] ? JSON.parse(row[1], BufferJSON.reviver) : {};
            console.log(`[DB] 📦 تم تحميل بيانات الجلسة بنجاح.`);
        } catch (e) {
            console.error(`[DB_ERROR] ⚠️ فشل تحليل JSON، سيتم البدء من الصفر.`);
            creds = initAuthCreds();
            keys = {};
        }

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
                        saveCreds();
                    }
                }
            },
            saveCreds
        };
    } catch (err) {
        console.error(`[FATAL_DB_ERROR] 💥 خطأ في مرحلة القاعدة: ${err.message}`);
        // العودة بحالة فارغة لكي لا يتوقف البوت تماماً
        return { state: { creds: initAuthCreds(), keys: {} }, saveCreds: () => {} };
    }
}

async function connectToWhatsApp() {
    console.log(`[WA] 🛠️ تهيئة المقبس...`);
    const { state, saveCreds } = await usePostgresAuthState(storeId);

    const sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        logger: pino({ level: "silent" }),
        browser: ["Jaddahh Bot", "Chrome", "1.0.0"],
        syncFullHistory: false,
        connectTimeoutMs: 30000, // مهلة 30 ثانية للاتصال بواتساب
    });

    // كود الربط (Pairing Code)
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
            console.log(`[QR] ✅ تم توليد الباركود بنجاح.`);
        }

        if (connection === "close") {
            const statusCode = (lastDisconnect.error instanceof Boom)?.output?.statusCode;
            if (statusCode !== DisconnectReason.loggedOut) {
                console.log(`[RECONNECT] 🔄 إعادة محاولة...`);
                setTimeout(() => connectToWhatsApp(), 5000);
            }
        } else if (connection === "open") {
            console.log(`[WA_READY] 🎉 الجلسة نشطة الآن.`);
            console.log(`SESSION_OPENED`);
        }
    });

    // الأوامر من Python
    process.stdin.on("data", async (data) => {
        const input = data.toString().trim();
        if (input.startsWith("SEND:")) {
            try {
                const [phone, ...msg] = input.substring(5).split("|");
                await sock.sendMessage(`${phone}@s.whatsapp.net`, { text: msg.join("|") });
            } catch (e) {}
        }
    });
}

connectToWhatsApp().catch(err => console.error(err));
