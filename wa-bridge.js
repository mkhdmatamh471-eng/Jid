require('dotenv').config();
const { 
    default: makeWASocket, 
    useMultiFileAuthState, 
    fetchLatestBaileysVersion, 
    DisconnectReason 
} = require("@whiskeysockets/baileys");
const pino = require("pino");
const fs = require('fs');
const path = require('path');
const { createClient } = require('@supabase/supabase-js');

// --- إعدادات Supabase ---
// تأكد من إضافة هذه المتغيرات في بيئة Render (Environment Variables)
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;
const supabase = createClient(supabaseUrl, supabaseKey);

// --- دوال المزامنة مع قاعدة البيانات ---
async function syncSessionToSupabase(storeId, sessionDir) {
    try {
        if (!fs.existsSync(sessionDir)) return;
        
        const files = fs.readdirSync(sessionDir);
        const sessionData = {};
        
        for (const file of files) {
            // نقوم بقراءة ملفات الجلسة (JSON فقط) لتخزينها
            if (file.endsWith('.json')) {
                const filePath = path.join(sessionDir, file);
                const fileContent = fs.readFileSync(filePath, 'utf-8');
                sessionData[file] = JSON.parse(fileContent);
            }
        }
        
        // رفع البيانات ككائن JSON واحد إلى عمود session_data
        const { error } = await supabase
            .from('stores') // استبدل 'stores' باسم جدولك الفعلي
            .upsert({ store_id: storeId, session_data: sessionData });
            
        if (error) throw error;
        // console.log(`☁️ [SYNC] Session synced to Supabase for Store: ${storeId}`);
    } catch (error) {
        console.error(`❌ [SYNC_ERROR] ${error.message}`);
    }
}

async function restoreSessionFromSupabase(storeId, sessionDir) {
    try {
        const { data, error } = await supabase
            .from('stores') // استبدل 'stores' باسم جدولك الفعلي
            .select('session_data')
            .eq('store_id', storeId)
            .single();

        if (error && error.code !== 'PGRST116') { // تجاهل خطأ "عدم وجود سجل"
            throw error;
        }

        if (data && data.session_data) {
            if (!fs.existsSync(sessionDir)) {
                fs.mkdirSync(sessionDir, { recursive: true });
            }
            // إعادة بناء الملفات في مجلد /tmp
            for (const [filename, content] of Object.entries(data.session_data)) {
                fs.writeFileSync(path.join(sessionDir, filename), JSON.stringify(content, null, 2));
            }
            console.log(`📥 [RESTORE] Session restored from Supabase for Store: ${storeId}`);
        }
    } catch (error) {
         console.error(`❌ [RESTORE_ERROR] ${error.message}`);
    }
}

// --- الدالة الأساسية لتشغيل واتساب ---
async function startWhatsApp(storeId) {
    // 1. استخدام مسار /tmp لأنه مسموح الكتابة فيه في بيئات الخوادم السحابية مثل Render
    const sessionDir = path.join('/tmp', `auth_info_${storeId}`);
    const qrFilePath = path.join(sessionDir, 'last_qr.txt');

    // 2. محاولة استرجاع الجلسة السابقة من قاعدة البيانات قبل التشغيل
    await restoreSessionFromSupabase(storeId, sessionDir);

    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
        version,
        auth: state,
        printQRInTerminal: false, 
        logger: pino({ level: "silent" }),
        browser: ["Ubuntu", "Chrome", "20.0.04"], // تغيير لتقليل الحظر
        syncFullHistory: false 
    });

    // 3. عند تحديث الاعتمادات، احفظها محلياً وارفعها إلى Supabase
    sock.ev.on("creds.update", async () => {
        await saveCreds();
        await syncSessionToSupabase(storeId, sessionDir);
    });

    sock.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log(`QR_DATA_START:${qr}:QR_DATA_END`);
            try { fs.writeFileSync(qrFilePath, qr, { flush: true }); } catch (err) {}
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
            } else {
                // إذا قام المستخدم بتسجيل الخروج من هاتفه، امسح الجلسة محلياً ومن قاعدة البيانات
                fs.rmSync(sessionDir, { recursive: true, force: true });
                await supabase.from('stores').update({ session_data: null }).eq('store_id', storeId);
                console.log(`🗑️ [CLEANUP] Session deleted for Store: ${storeId}`);
            }
        } else if (connection === "open") {
            console.log(`SESSION_OPENED:${storeId}`);
            // رفع نهائي بعد فتح الاتصال لضمان حفظ كل المفاتيح
            await syncSessionToSupabase(storeId, sessionDir);

            if (fs.existsSync(qrFilePath)) {
                setTimeout(() => {
                    try { fs.unlinkSync(qrFilePath); } catch(e) {}
                }, 2000); 
            }
        }
    });

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
