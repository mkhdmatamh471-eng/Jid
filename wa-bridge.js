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
    // 1. استخدام مسار مطلق متوافق مع بايثون
    const rootDir = process.cwd(); 
    const sessionDir = path.join(rootDir, `auth_info_${storeId}`);
    const qrFilePath = path.join(sessionDir, 'last_qr.txt');

    if (!fs.existsSync(sessionDir)) {
        fs.mkdirSync(sessionDir, { recursive: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
        version,
        auth: state,
        printQRInTerminal: false, 
        logger: pino({ level: "silent" }),
        browser: ["Jaddah Bot", "Chrome", "1.0.0"],
        syncFullHistory: false 
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", (update) => {
        const { connection, lastDisconnect, qr } = update;

        // --- نظام التمرير المباشر للبصمة (QR) ---
        if (qr) {
            // نطبع الكود بعلامات محددة ليلتقطها كود بايثون من الـ stdout فوراً
            console.log(`QR_DATA_START:${qr}:QR_DATA_END`);
            
            // احتياطاً نكتب الملف أيضاً
            try {
                fs.writeFileSync(qrFilePath, qr, { flush: true });
            } catch (err) {}
        }

        if (connection === "close") {
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
            
            console.log(`SESSION_CLOSED:${storeId}:RECONNECT:${shouldReconnect}`);

            if (fs.existsSync(qrFilePath)) {
                try { fs.unlinkSync(qrFilePath); } catch(e) {}
            }

            if (shouldReconnect) {
                startWhatsApp(storeId);
            }
        } else if (connection === "open") {
            // علامة النجاح ليعرف بايثون أن الربط تم
            console.log(`SESSION_OPENED:${storeId}`);
            
            if (fs.existsSync(qrFilePath)) {
                setTimeout(() => {
                    try { fs.unlinkSync(qrFilePath); } catch(e) {}
                }, 2000); 
            }
        }
    });

    // استقبال أوامر الإرسال من Python عبر stdin
    process.stdin.on("data", async (data) => {
        try {
            const str = data.toString().trim();
            if (str.startsWith("SEND:")) {
                const parts = str.replace("SEND:", "").split("|");
                if (parts.length >= 2) {
                    const rawJid = parts[0];
                    const jid = rawJid.includes("@") ? rawJid : `${rawJid}@s.whatsapp.net`;
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
    console.log(`[BRIDGE_STARTED] Target Store: ${storeId}`);
    startWhatsApp(storeId).catch(err => console.error("CRITICAL_NODE_ERROR:", err));
} else {
    process.exit(1);
}
