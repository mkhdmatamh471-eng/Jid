const { 
    default: makeWASocket, 
    useMultiFileAuthState, 
    fetchLatestBaileysVersion, 
    DisconnectReason 
} = require("@whiskeysockets/baileys");
const pino = require("pino");
const fs = require('fs');
const path = require('path');

async function startWhatsApp(storeId) {
    // 1. إعداد مسار الجلسة والملفات
    const sessionDir = path.join(__dirname, `auth_info_${storeId}`);
    const qrFilePath = path.join(sessionDir, 'last_qr.txt');

    if (!fs.existsSync(sessionDir)) {
        fs.mkdirSync(sessionDir, { recursive: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
    const { version } = await fetchLatestBaileysVersion();

    // 2. إنشاء اتصال Baileys
    const sock = makeWASocket({
        version,
        auth: state,
        printQRInTerminal: true, 
        logger: pino({ level: "silent" }),
        browser: ["Jaddah Bot", "Chrome", "1.0.0"],
        syncFullHistory: false // لتقليل استهلاك الرام في ريندر
    });

    // حفظ بيانات الاعتماد عند تحديثها
    sock.ev.on("creds.update", saveCreds);

    // 3. مراقبة حالة الاتصال والباركود
    sock.ev.on("connection.update", (update) => {
        const { connection, lastDisconnect, qr } = update;

        // معالجة الباركود
        if (qr) {
            fs.writeFileSync(qrFilePath, qr);
            console.log(`[QR_CREATED] Store: ${storeId}`);
            // طباعة للـ logs لسهولة المتابعة
            console.log(`SESSION_QR:${storeId}:${qr}`);
        }

        // معالجة الانفصال وإعادة الاتصال
        if (connection === "close") {
            const shouldReconnect = (lastDisconnect.error)?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log(`[CONNECTION_CLOSED] Store: ${storeId}, Reason: ${shouldReconnect ? 'Reconnecting...' : 'Logged Out'}`);
            
            if (shouldReconnect) {
                startWhatsApp(storeId);
            } else {
                // إذا سجل الخروج يدوياً، نمسح ملف الباركود القديم
                if (fs.existsSync(qrFilePath)) fs.unlinkSync(qrFilePath);
            }
        } else if (connection === "open") {
            console.log(`SESSION_OPENED:${storeId}`);
            // مسح ملف الباركود بعد النجاح لأنه لم يعد مطلوباً
            if (fs.existsSync(qrFilePath)) fs.unlinkSync(qrFilePath);
        }
    });

    // 4. استقبال أوامر الإرسال من FastAPI (Python)
    process.stdin.on("data", async (data) => {
        try {
            const str = data.toString().trim();
            if (str.startsWith("SEND:")) {
                const parts = str.replace("SEND:", "").split("|");
                if (parts.length >= 2) {
                    const remoteJid = parts[0];
                    const message = parts[1];
                    
                    await sock.sendMessage(remoteJid, { text: message });
                    console.log(`[SUCCESS_SEND] To: ${remoteJid}`);
                }
            }
        } catch (err) {
            console.error(`[SEND_ERROR] Store: ${storeId}, Error: ${err.message}`);
        }
    });
}

// تشغيل الجلسة للمتجر الممرر كـ Argument
const storeId = process.argv[2];
if (storeId) {
    startWhatsApp(storeId).catch(err => console.error("CRITICAL_ERROR:", err));
} else {
    console.error("ERROR: No Store ID provided!");
    process.exit(1);
}
