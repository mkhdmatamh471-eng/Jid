console.log("DEBUG: Script started, checking DB connection...");
const { 
    default: makeWASocket, 
    DisconnectReason, 
    initAuthCreds, 
    BufferJSON, 
    proto, 
    useMultiFileAuthState 
} = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const pino = require("pino");
const { Client } = require("pg");

// جلب المتغيرات من النظام
const storeId = process.argv[2] || "default";
const phoneNumber = process.argv[3]; // رقم الهاتف في حال طلب كود الربط

console.log(`[START] 🚀 بدء تشغيل الجسر للمتجر: ${storeId}`);

/**
 * إعداد الاتصال بقاعدة البيانات PostgreSQL (Supabase)
 */
const dbClient = new Client({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false } 
});

/**
 * محرك إدارة الجلسة المطور مع تسجيل دقيق للأخطاء
 */
async function usePostgresAuthState(storeId) {
    console.log(`[DB] 🔄 محاولة الاتصال بقاعدة البيانات لـ ${storeId}...`);
    try {
        await dbClient.connect();
        console.log(`[DB] ✅ تم الاتصال بقاعدة البيانات بنجاح.`);
    } catch (e) {
        console.error(`[DB_ERROR] ❌ فشل الاتصال بالقاعدة: ${e.message}`);
    }

    // جلب البيانات
    console.log(`[DB] 🔍 جلب بيانات الجلسة من الجدول...`);
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
            // لا نطبع رسالة حفظ الـ Keys في كل مرة لتجنب ملء الـ Logs
        } catch (err) {
            console.error(`[SAVE_ERROR] ❌ فشل حفظ الجلسة في القاعدة: ${err.message}`);
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
}

async function connectToWhatsApp() {
    console.log(`[WA] 🛠️ يجري إعداد مقبس الواتساب (Socket)...`);
    const { state, saveCreds } = await usePostgresAuthState(storeId);

    const sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        logger: pino({ level: "silent" }),
        browser: ["Jaddahh Bot", "Chrome", "1.0.0"],
        syncFullHistory: false, 
    });

    // --- دعم كود الربط (Pairing Code) ---
    if (!sock.authState.creds.registered && phoneNumber) {
        console.log(`[PAIRING] 🔑 طلب كود ربط للرقم: ${phoneNumber}`);
        setTimeout(async () => {
            try {
                const code = await sock.requestPairingCode(phoneNumber.replace(/\D/g, ''));
                console.log(`PAIRING_CODE_START:${code}:PAIRING_CODE_END`);
                console.log(`[PAIRING] ✅ الكود المستلم: ${code}`);
            } catch (err) {
                console.error(`[PAIRING_ERROR] ❌ فشل طلب الكود: ${err.message}`);
            }
        }, 5000); // تأخير لضمان جاهزية الاتصال
    }

    // تحديث بيانات الاعتماد
    sock.ev.on("creds.update", async () => {
        console.log(`[WA] 📥 تحديث بيانات الاعتماد (Creds Update)...`);
        await saveCreds();
    });

    // مراقبة حالة الاتصال والباركود
    sock.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log(`[QR] 📸 تم توليد باركود جديد.`);
            console.log(`QR_DATA_START:${qr}:QR_DATA_END`);
        }

        if (connection === "close") {
            const statusCode = (lastDisconnect.error instanceof Boom)?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
            
            console.log(`[WA_CLOSED] ⚠️ انقطع الاتصال. الحالة: ${statusCode}. إعادة المحاولة: ${shouldReconnect}`);
            
            if (shouldReconnect) {
                console.log(`[RECONNECT] 🔄 جاري محاولة إعادة الاتصال خلال 5 ثوانٍ...`);
                setTimeout(() => connectToWhatsApp(), 5000);
            } else {
                console.log(`[LOGOUT] 🚪 تم تسجيل الخروج بنجاح من الجلسة.`);
            }
        } else if (connection === "open") {
            console.log(`[WA_READY] 🎉 تم فتح الجلسة بنجاح! الواتساب الآن نشط.`);
        }
    });

    // معالجة الأوامر من Python
    process.stdin.on("data", async (data) => {
        const input = data.toString().trim();
        if (input.startsWith("SEND:")) {
            try {
                const payload = input.substring(5);
                const [phone, ...msgArr] = payload.split("|");
                const message = msgArr.join("|");
                
                console.log(`[OUTGOING] 📤 إرسال رسالة إلى ${phone}...`);
                await sock.sendMessage(`${phone}@s.whatsapp.net`, { text: message });
                console.log(`SENT_CONFIRMATION:${phone}`);
            } catch (e) {
                console.error(`[SEND_ERROR] ❌ فشل إرسال الرسالة: ${e.message}`);
            }
        }
    });

    // معالجة الرسائل الواردة
    sock.ev.on("messages.upsert", async (m) => {
        if (m.type !== "notify") return;
        
        for (const msg of m.messages) {
            if (!msg.key.fromMe && msg.message) {
                const sender = msg.key.remoteJid.split("@")[0];
                const text = msg.message.conversation || 
                             msg.message.extendedTextMessage?.text || 
                             msg.message.buttonsResponseMessage?.selectedButtonId;

                if (text) {
                    console.log(`[INCOMING] 📥 رسالة من ${sender}: ${text}`);
                    console.log(`NEW_MSG|${sender}|${text}`);
                }
            }
        }
    });
}

// البدء مع التقاط أخطاء التشغيل الأولية
connectToWhatsApp().catch(err => {
    console.error("[CRITICAL_ERROR] 💥 خطأ قاتل في الجسر:", err);
});
