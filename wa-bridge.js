// wa-bridge.js
const { default: makeWASocket, useMultiFileAuthState, fetchLatestBaileysVersion } = require("@whiskeysockets/baileys");
const pino = require("pino");
const { QRCodeTerminal } = require("qrcode-terminal");

async function startWhatsApp(storeId) {
    // تحديد مكان حفظ الجلسة لكل متجر بشكل منفصل في قاعدة بياناتك أو مجلد
    const { state, saveCreds } = await useMultiFileAuthState(`auth_info_${storeId}`);
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
        version,
        auth: state,
        printQRInTerminal: true, // سيظهر الباركود في سجلات Render
        logger: pino({ level: "silent" }),
        browser: ["Jaddah Bot", "Chrome", "1.0.0"]
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", (update) => {
        const { connection, lastDisconnect, qr } = update;
        if (qr) {
            // هنا نرسل الباركود لـ FastAPI (عبر Webhook داخلي أو ملف)
            console.log(`SESSION_QR:${storeId}:${qr}`);
        }
        if (connection === "close") {
            console.log(`SESSION_CLOSED:${storeId}`);
            startWhatsApp(storeId); // إعادة اتصال تلقائي
        } else if (connection === "open") {
            console.log(`SESSION_OPENED:${storeId}`);
        }
    });

    // استقبال أوامر الإرسال من FastAPI عبر Standard Input (stdin)
    process.stdin.on("data", async (data) => {
        const str = data.toString().trim();
        if (str.startsWith("SEND:")) {
            const [_, remoteJid, message] = str.split("|");
            await sock.sendMessage(remoteJid, { text: message });
        }
    });
}

// تشغيل الجلسة للمتجر الممرر كـ Argument
const storeId = process.argv[2];
if (storeId) startWhatsApp(storeId);
