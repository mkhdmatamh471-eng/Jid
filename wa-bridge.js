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
    // 1. إعداد المسارات (استخدام المسار المطلق لضمان التوافق مع Python)
    const rootDir = process.cwd(); // هذا يضمن التوافق مع os.getcwd() في بايثon
    const sessionDir = path.join(rootDir, `auth_info_${storeId}`);
    const qrFilePath = path.join(sessionDir, 'last_qr.txt');

    console.log(`[NODE_START] Root: ${rootDir}`);
    console.log(`[NODE_START] Session Path: ${sessionDir}`);

    if (!fs.existsSync(sessionDir)) {
        fs.mkdirSync(sessionDir, { recursive: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
        version,
        auth: state,
        printQRInTerminal: false, // سنعتمد على الملف والـ logs فقط
        logger: pino({ level: "silent" }),
        browser: ["Jaddah Bot", "Chrome", "1.0.0"],
        syncFullHistory: false 
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", (update) => {
        const { connection, lastDisconnect, qr } = update;

        // --- معالجة الباركود ---
        if (qr) {
            try {
                // حفظ الباركود ومزامنة الكتابة فوراً للقرص
                fs.writeFileSync(qrFilePath, qr, { flush: true });
                console.log(`[QR_CREATED] Store: ${storeId}`);
                console.log(`SESSION_QR:${storeId}:${qr}`); // للرصد في الـ Logs
            } catch (err) {
                console.error(`[QR_WRITE_ERROR] ${err.message}`);
            }
        }

        // --- معالجة الحالات ---
        if (connection === "close") {
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
            
            console.log(`[CONN_CLOSED] Store: ${storeId}, Status: ${statusCode}, Reconnecting: ${shouldReconnect}`);

            // تنظيف الملفات عند تسجيل الخروج أو الخطأ
            if (fs.existsSync(qrFilePath)) fs.unlinkSync(qrFilePath);

            if (shouldReconnect) {
                startWhatsApp(storeId);
            }
        } else if (connection === "open") {
            console.log(`SESSION_OPENED:${storeId}`);
            // مسح الباركود فور الاتصال لتجنب استخدامه مرة أخرى
            if (fs.existsSync(qrFilePath)) {
                setTimeout(() => fs.unlinkSync(qrFilePath), 2000); 
            }
        }
    });

    // استقبال أوامر الإرسال من Python
    process.stdin.on("data", async (data) => {
        try {
            const str = data.toString().trim();
            if (str.startsWith("SEND:")) {
                const parts = str.replace("SEND:", "").split("|");
                if (parts.length >= 2) {
                    const jid = parts[0].includes("@s.whatsapp.net") ? parts[0] : `${parts[0]}@s.whatsapp.net`;
                    await sock.sendMessage(jid, { text: parts[1] });
                    console.log(`[SUCCESS_SEND] To: ${jid}`);
                }
            }
        } catch (err) {
            console.error(`[SEND_ERROR] ${err.message}`);
        }
    });
}

const storeId = process.argv[2];
if (storeId) {
    startWhatsApp(storeId).catch(err => console.error("CRITICAL_NODE_ERROR:", err));
} else {
    process.exit(1);
}
