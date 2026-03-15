<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة تحكم بوت سلة الذكي | AI Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/toastify-js/src/toastify.min.css">
    <script type="text/javascript" src="https://cdn.jsdelivr.net/npm/toastify-js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

    <style>
        body { font-family: 'Cairo', sans-serif; }
        .qr-gradient { background: linear-gradient(135deg, #f6f8fb 0%, #e9eff5 100%); }
    </style>
</head>
<body class="bg-gray-50 text-gray-800">

    <div class="min-h-screen p-4 md:p-8">
        <header class="max-w-6xl mx-auto mb-8 flex flex-col md:flex-row justify-between items-center gap-4">
            <div>
                <h1 class="text-3xl font-bold text-gray-900">لوحة تحكم البوت الذكي 🤖</h1>
                <p class="text-gray-500">مرحباً بك يا محمد، يمكنك متابعة أداء الذكاء الاصطناعي وتخصيص الإعدادات.</p>
            </div>
            <div class="flex items-center gap-3">
                <span class="flex h-3 w-3 rounded-full bg-green-500"></span>
                <span class="bg-green-100 text-green-700 px-4 py-2 rounded-full font-bold text-sm">الجلسة نشطة</span>
            </div>
        </header>

        <div class="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-10">
    
    <div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 border-r-4 border-r-green-500">
        <p class="text-gray-500 text-sm font-semibold">أرباح مستردة (بالريال) 💰</p>
        <h2 class="text-4xl font-black text-green-600 mt-1" id="recoveredRevenue">--</h2>
        <p class="text-[10px] text-gray-400 mt-1">بناءً على السلال التي أكمل البوت استردادها</p>
    </div>

    <div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
        <p class="text-gray-500 text-sm font-semibold">إجمالي ردود البوت</p>
        <h2 class="text-4xl font-black text-gray-900 mt-1" id="botUsage">--</h2>
    </div>
    
    <div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
        <p class="text-gray-500 text-sm font-semibold">سلال متروكة</p>
        <h2 class="text-4xl font-black text-orange-500 mt-1" id="abandonedCount">--</h2>
    </div>

    <div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
        <p class="text-gray-500 text-sm font-semibold">دقة AI</p>
        <h2 class="text-4xl font-black text-blue-500 mt-1">98.4%</h2>
    </div>
</div>
<div class="max-w-6xl mx-auto mb-10">
    <div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
        <h3 class="text-xl font-bold mb-6">مخطط الاسترداد الأسبوعي 📈</h3>
        <canvas id="recoveryChart" class="w-full h-[250px]"></canvas>
    </div>
</div>

        <div class="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="lg:col-span-2 bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden h-fit">
                <div class="p-6 border-b border-gray-50 flex justify-between items-center">
                    <h3 class="text-xl font-bold">آخر المحادثات</h3>
                    <button onclick="loadDashboard()" class="text-blue-600 text-sm hover:underline">تحديث 🔄</button>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-right">
                        <thead class="bg-gray-50 text-gray-500 text-sm">
                            <tr>
                                <th class="p-4">العميل</th>
                                <th class="p-4">آخر رسالة</th>
                                <th class="p-4 text-center">الحالة</th>
                            </tr>
                        </thead>
                        <tbody id="recentChats"></tbody>
                    </table>
                </div>
            </div>

            <div class="space-y-8">
                
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 text-center">
                    <h3 class="text-lg font-bold mb-4">ربط واتساب مباشر 📱</h3>
                    <div id="qr-box" class="qr-gradient inline-block p-4 rounded-2xl border-2 border-dashed border-gray-200 transition-all duration-500">
                        <img id="qr-image" src="https://via.placeholder.com/200?text=Scan+QR" class="w-48 h-48 mx-auto rounded-lg shadow-inner" alt="QR Code">
                    </div>
                    <p class="text-[11px] text-gray-500 mt-4 leading-relaxed">
                        افتح واتساب > الأجهزة المرتبطة > ربط جهاز <br>
                        ثم قم بمسح الكود أعلاه.
                    </p>
                    <button onclick="refreshQR()" class="mt-4 w-full py-2 text-blue-600 text-sm font-bold border border-blue-100 rounded-xl hover:bg-blue-50 transition">
                        توليد كود جديد 🔄
                    </button>
                </div>

                <div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
                    <h3 class="text-lg font-bold mb-6">إعدادات الذكاء</h3>
                    <div class="space-y-5">
                        <div>
                            <label class="block text-sm font-semibold text-gray-700 mb-2">رقم المسؤول</label>
                            <input type="text" id="adminPhone" placeholder="9665xxxxxxxx" 
                                   class="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none transition">
                        </div>
                        <div>
                            <label class="block text-sm font-semibold text-gray-700 mb-2">تعليمات البوت (Prompt)</label>
                            <textarea id="systemPrompt" rows="4" 
                                      class="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none transition"
                                      placeholder="أنت مساعد ذكي لمتجر..."></textarea>
                        </div>
                        <button onclick="saveSettings()" id="saveBtn" 
                                class="w-full bg-gray-900 text-white py-4 rounded-xl font-bold hover:bg-black transition shadow-lg">
                            حفظ الإعدادات
                        </button>
                    </div>
                </div>

            </div>
        </div>
    </div>

    <script>
        const storeId = "STORE_001";

        // تعريف متغير خارج الدالة للاحتفاظ بمرجع الرسم البياني
let recoveryChartInstance = null;

        async function loadDashboard() {
    try {
        const response = await fetch(`/admin/dashboard/${storeId}`);
        const data = await response.json();

        // 1. تحديث الأرقام العلوية مع تأثير بسيط (اختياري)
        document.getElementById('botUsage').innerText = Number(data.bot_usage).toLocaleString() || 0;
        document.getElementById('abandonedCount').innerText = data.salla_stats.abandoned_carts_count || 0;
        
        // تحديث الربح المسترد بإضافة رمز العملة
        const revenueElem = document.getElementById('recoveredRevenue');
        revenueElem.innerText = `${Number(data.summary.total_revenue_saved).toLocaleString()} ر.س`;

        // 2. تحديث جدول المحادثات (تأكد من وجود هذا الجزء)
        const chatTable = document.getElementById('recentChats');
        if (data.recent_activity) {
            chatTable.innerHTML = data.recent_activity.map(chat => `
                <tr class="border-b border-gray-50 hover:bg-gray-50 transition">
                    <td class="p-4 font-bold text-xs">${chat.customers.phone_number}</td>
                    <td class="p-4 text-xs text-gray-600 truncate max-w-[150px]">${chat.content}</td>
                    <td class="p-4 text-center">
                        <span class="px-2 py-1 rounded-full text-[9px] font-bold ${chat.role === 'assistant' ? 'bg-blue-100 text-blue-600' : 'bg-green-100 text-green-600'}">
                            ${chat.role === 'assistant' ? '🤖 آلي' : '👤 عميل'}
                        </span>
                    </td>
                </tr>
            `).join('');
        }

        // 3. إدارة المخطط البياني (Chart.js)
        const ctx = document.getElementById('recoveryChart').getContext('2d');

        // الحماية من تداخل الرسوم: إذا كان هناك رسم سابق، قم بحذفه
        if (recoveryChartInstance) {
            recoveryChartInstance.destroy();
        }

        // إنشاء الرسم البياني الجديد
        recoveryChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.charts_data.labels, 
                datasets: [{
                    label: 'أرباح مستردة (ر.س)',
                    data: data.charts_data.values, 
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    borderWidth: 2
                }]
            },
            options: { 
                responsive: true, 
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false } // إخفاء الليبل العلوي لجمالية التصميم
                },
                scales: {
                    y: { beginAtZero: true, grid: { display: false } },
                    x: { grid: { display: false } }
                }
            }
        });

    } catch (error) { 
        console.error("Dashboard Sync Error:", error); 
    }
}


        async function refreshQR() {
            const qrImage = document.getElementById('qr-image');
            const qrBox = document.getElementById('qr-box');
            qrBox.style.opacity = "0.3";
            
            try {
                const response = await fetch(`/admin/get-qr/${storeId}`);
                const data = await response.json();
                if (data.qr_code) {
                    qrImage.src = data.qr_code;
                } else {
                    alert("فشل جلب الكود، قد تكون الجلسة نشطة بالفعل.");
                }
            } catch (err) { alert("حدث خطأ أثناء الاتصال بالسيرفر"); }
            finally { qrBox.style.opacity = "1"; }
        }

        async function saveSettings() {
            const btn = document.getElementById('saveBtn');
            const payload = {
                admin_phone: document.getElementById('adminPhone').value,
                system_prompt: document.getElementById('systemPrompt').value
            };
            btn.innerText = "جاري الحفظ...";
            btn.disabled = true;
            try {
                const resp = await fetch(`/admin/update-config/${storeId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (resp.ok) alert("✅ تم الحفظ!");
            } catch (err) { alert("❌ خطأ!"); }
            finally { 
                btn.innerText = "حفظ الإعدادات"; 
                btn.disabled = false; 
            }
        }

        loadDashboard();
        setInterval(loadDashboard, 60000);
    </script>
</body>
</html>
