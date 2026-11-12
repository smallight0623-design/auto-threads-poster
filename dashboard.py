import os
import sys
import json
import subprocess
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import account_manager

app = FastAPI(title="Threads 矩陣多帳號自動發布主控台")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

REGIONS = [
    "台灣 (繁體中文)",
    "越南 (Tiếng Việt)",
    "日本 (日本語)",
    "韓國 (한국어)",
    "香港 (繁體中文)",
    "北美 (English)"
]

@app.get("/api/data")
async def get_dashboard_data():
    """回傳所有帳號、狀態與全域設定，供前端動態渲染與輪詢"""
    accounts = account_manager.get_accounts()
    global_settings = account_manager.get_global_settings()
    
    accounts_detail = []
    for acc in accounts:
        acc_id = acc["id"]
        status = account_manager.get_account_status(acc_id)
        error = account_manager.get_account_error(acc_id)
        session_content = account_manager.get_account_session_content(acc_id)
        has_session = bool(session_content)

        accounts_detail.append({
            **acc,
            "has_session": has_session,
            "session_length": len(session_content) if has_session else 0,
            "status": status,
            "error": error
        })

    return JSONResponse({
        "global_settings": global_settings,
        "accounts": accounts_detail
    })

@app.post("/api/global-settings")
async def save_global_settings_api(request: Request):
    data = await request.json()
    account_manager.save_global_settings(data)
    return JSONResponse({"status": "success", "message": "全域 AI 設定已儲存"})

@app.post("/api/accounts/save")
async def save_account_api(request: Request):
    payload = await request.json()
    session_data = payload.pop("session_data", None)
    acc_id = account_manager.save_account(payload, session_data_str=session_data)
    return JSONResponse({"status": "success", "account_id": acc_id})

@app.post("/api/accounts/{acc_id}/toggle")
async def toggle_account_api(acc_id: str):
    acc = account_manager.get_account(acc_id)
    if acc:
        acc["enabled"] = not acc.get("enabled", True)
        account_manager.save_account(acc)
        return JSONResponse({"status": "success", "enabled": acc["enabled"]})
    return JSONResponse({"status": "error", "message": "帳號不存在"}, status_code=404)

@app.post("/api/accounts/{acc_id}/delete")
async def delete_account_api(acc_id: str):
    account_manager.delete_account(acc_id)
    return JSONResponse({"status": "success"})

@app.get("/api/accounts/{acc_id}/session")
async def get_session_api(acc_id: str):
    session_content = account_manager.get_account_session_content(acc_id)
    return JSONResponse({"session": session_content})

@app.post("/api/accounts/{acc_id}/trigger")
async def trigger_account_api(acc_id: str):
    """為指定單一帳號在背景觸發執行"""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "main.py"), "--account", acc_id], cwd=BASE_DIR, env=env)
    return JSONResponse({"status": "triggered", "account_id": acc_id})

@app.post("/api/trigger-all")
async def trigger_all_api():
    """為所有已啟用的帳號在背景觸發批次執行"""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "main.py"), "--all"], cwd=BASE_DIR, env=env)
    return JSONResponse({"status": "triggered_all"})

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    regions_json = json.dumps(REGIONS, ensure_ascii=False)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-TW" class="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Threads 矩陣多帳號自動發布主控台</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            tailwind.config = {{ darkMode: 'class' }}
        </script>
        <style>
            /* 自訂捲軸樣式 */
            ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
            ::-webkit-scrollbar-track {{ background: #0f172a; }}
            ::-webkit-scrollbar-thumb {{ background: #334155; border-radius: 4px; }}
            ::-webkit-scrollbar-thumb:hover {{ background: #475569; }}
        </style>
    </head>
    <body class="bg-gray-950 text-gray-100 min-h-screen p-4 md:p-8 font-sans">
        <div class="max-w-6xl mx-auto space-y-6">
            
            <!-- 頂部導航與主標題列 -->
            <div class="flex flex-col md:flex-row md:items-center justify-between border-b border-gray-800 pb-5 gap-4">
                <div>
                    <h1 class="text-2xl font-bold text-white flex items-center gap-2">
                        🚀 Threads 矩陣社群多帳號自動搬運主控台
                    </h1>
                    <p class="text-xs text-gray-400 mt-1">
                        每組 Cookie 獨立工作台 ‧ 各帳號獨立地區與遊戲詞庫 ‧ 支援單一或批次點火發布
                    </p>
                </div>
                <div class="flex flex-wrap items-center gap-2.5">
                    <button onclick="openGlobalSettingsModal()" class="bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 px-3.5 py-2 rounded-xl text-xs font-semibold transition flex items-center gap-1.5">
                        <span>🧠 AI 中轉大腦設定</span>
                    </button>
                    <button onclick="openAddAccountModal()" class="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-xl text-xs font-bold transition shadow-lg shadow-indigo-600/30 flex items-center gap-1.5">
                        <span>➕ 新增社群帳號工作台</span>
                    </button>
                    <button id="btn-trigger-all" onclick="triggerAllAccounts()" class="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-xl text-xs font-bold transition shadow-lg shadow-emerald-900/30 flex items-center gap-1.5">
                        <span>⚡ 一鍵點火所有啟用帳號</span>
                    </button>
                </div>
            </div>

            <!-- 總覽狀態指標條 -->
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div class="bg-gray-900/80 border border-gray-800 p-4 rounded-xl">
                    <span class="text-xs text-gray-400 block">帳號工作台總數</span>
                    <span id="stat-total" class="text-xl font-bold text-white mt-1 block">0</span>
                </div>
                <div class="bg-gray-900/80 border border-gray-800 p-4 rounded-xl">
                    <span class="text-xs text-gray-400 block">啟用中工作台</span>
                    <span id="stat-enabled" class="text-xl font-bold text-emerald-400 mt-1 block">0</span>
                </div>
                <div class="bg-gray-900/80 border border-gray-800 p-4 rounded-xl">
                    <span class="text-xs text-gray-400 block">AI 模型代號</span>
                    <span id="stat-model" class="text-xs font-mono font-bold text-purple-300 mt-2 block truncate">--</span>
                </div>
                <div class="bg-gray-900/80 border border-gray-800 p-4 rounded-xl">
                    <span class="text-xs text-gray-400 block">中轉站狀態</span>
                    <span id="stat-relay" class="text-xs font-semibold text-blue-400 mt-2 block truncate">連線正常</span>
                </div>
            </div>

            <!-- 帳號工作台卡片列表 (Accounts Grid) -->
            <div class="space-y-4">
                <div class="flex items-center justify-between">
                    <h2 class="text-base font-bold text-gray-200 flex items-center gap-2">
                        <span>🏢 帳號工作台列表</span>
                    </h2>
                    <span class="text-xs text-gray-400">每 2 秒自動更新即時發布進度</span>
                </div>

                <div id="accounts-container" class="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <!-- 動態渲染卡片 -->
                    <div class="col-span-full text-center py-12 text-gray-500">正在載入帳號工作台...</div>
                </div>
            </div>

        </div>

        <!-- =================== Modal 1: 新增 / 編輯帳號工作台 =================== -->
        <div id="modal-account" class="hidden fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div class="bg-gray-900 border border-gray-700 w-full max-w-xl rounded-2xl p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
                <div class="flex items-center justify-between border-b border-gray-800 pb-3">
                    <h3 id="modal-account-title" class="text-base font-bold text-white flex items-center gap-2">
                        <span>➕ 新增社群帳號工作台</span>
                    </h3>
                    <button onclick="closeAccountModal()" class="text-gray-400 hover:text-white text-lg font-mono">&times;</button>
                </div>

                <form id="form-account" onsubmit="handleAccountFormSubmit(event)" class="space-y-4 text-xs">
                    <input type="hidden" id="acc-id" name="id" value="">

                    <div>
                        <label class="block text-gray-300 font-medium mb-1">帳號自訂名稱 / 代號（辨識用）*</label>
                        <input id="acc-name" name="name" required placeholder="例如：@my_threads_tw 或 dinosaur.56467484" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none">
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-gray-300 font-medium mb-1">目標地區與語言 (受眾)*</label>
                            <select id="acc-region" name="target_region" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none">
                                <!-- 動態填入地區 -->
                            </select>
                        </div>
                        <div>
                            <label class="block text-gray-300 font-medium mb-1">特定遊戲名稱 (專有名詞對齊)*</label>
                            <input id="acc-game" name="game_name" required placeholder="例如：Monster Hunter Wilds / 原神" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none">
                        </div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-gray-300 font-medium mb-1">監控 Subreddit 板塊*</label>
                            <input id="acc-subreddit" name="subreddit" required placeholder="例如：MonsterHunter" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none">
                        </div>
                        <div>
                            <label class="block text-gray-300 font-medium mb-1">最低熱門讚數 (Upvotes)*</label>
                            <input type="number" id="acc-upvotes" name="min_upvotes" required value="100" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none">
                        </div>
                    </div>

                    <div>
                        <div class="flex items-center justify-between mb-1">
                            <label class="text-gray-300 font-medium">該帳號專屬 Threads Cookie Session (JSON)</label>
                            <span class="text-gray-500 text-[10px]">貼入 login_local.py 產生的內容</span>
                        </div>
                        <textarea id="acc-session" name="session_data" rows="4" placeholder='{{"cookies": [...], "origins": [...]}}' class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2 text-xs font-mono text-gray-300 focus:border-amber-500 focus:outline-none"></textarea>
                    </div>

                    <div class="flex items-center gap-2 pt-1">
                        <input type="checkbox" id="acc-enabled" name="enabled" class="rounded bg-gray-950 border-gray-700 text-indigo-600 focus:ring-0" checked>
                        <label for="acc-enabled" class="text-gray-300 cursor-pointer">立即啟用此帳號工作台</label>
                    </div>

                    <div class="flex justify-end gap-2 pt-3 border-t border-gray-800">
                        <button type="button" onclick="closeAccountModal()" class="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 font-medium">取消</button>
                        <button type="submit" class="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold shadow-lg shadow-indigo-600/30">儲存工作台</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- =================== Modal 2: AI 中轉大腦設定 =================== -->
        <div id="modal-global-settings" class="hidden fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div class="bg-gray-900 border border-gray-700 w-full max-w-lg rounded-2xl p-6 shadow-2xl space-y-4">
                <div class="flex items-center justify-between border-b border-gray-800 pb-3">
                    <h3 class="text-base font-bold text-white flex items-center gap-2">
                        <span>🧠 全域 AI 中轉站大腦設定</span>
                    </h3>
                    <button onclick="closeGlobalSettingsModal()" class="text-gray-400 hover:text-white text-lg font-mono">&times;</button>
                </div>

                <form onsubmit="handleGlobalSettingsSubmit(event)" class="space-y-4 text-xs">
                    <div>
                        <label class="block text-gray-300 font-medium mb-1">中轉站 Base URL (Endpoint)*</label>
                        <input id="global-base-url" required placeholder="https://api.your-relay.com/v1" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm font-mono text-gray-100 focus:border-purple-500 focus:outline-none">
                    </div>

                    <div>
                        <label class="block text-gray-300 font-medium mb-1">中轉站 API Key (密鑰)*</label>
                        <input type="password" id="global-api-key" placeholder="sk-..." class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm font-mono text-gray-100 focus:border-purple-500 focus:outline-none">
                    </div>

                    <div>
                        <label class="block text-gray-300 font-medium mb-1">模型代號 (Model Name)*</label>
                        <input id="global-model" required placeholder="gemini-2.5-flash" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm font-mono text-gray-100 focus:border-purple-500 focus:outline-none">
                        <p class="text-[11px] text-gray-500 mt-1">支援 gemini-2.5-flash / gemini-3.8-flash / gpt-4o-mini 等相容模型</p>
                    </div>

                    <div class="flex justify-end gap-2 pt-3 border-t border-gray-800">
                        <button type="button" onclick="closeGlobalSettingsModal()" class="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 font-medium">取消</button>
                        <button type="submit" class="px-5 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-bold shadow-lg shadow-purple-600/30">儲存 AI 設定</button>
                    </div>
                </form>
            </div>
        </div>

        <script>
            const AVAILABLE_REGIONS = {regions_json};
            let currentData = null;
            let activePolling = null;

            // 初始化與輪詢
            async function fetchDashboardData() {{
                try {{
                    const res = await fetch('/api/data');
                    currentData = await res.json();
                    renderDashboard(currentData);
                }} catch (e) {{
                    console.error("資料載入失敗:", e);
                }}
            }}

            function renderDashboard(data) {{
                const accounts = data.accounts || [];
                const global = data.global_settings || {{}};

                // 更新頂部指標
                document.getElementById('stat-total').innerText = accounts.length;
                document.getElementById('stat-enabled').innerText = accounts.filter(a => a.enabled).length;
                document.getElementById('stat-model').innerText = global.AI_MODEL || '未設定';
                document.getElementById('stat-relay').innerText = global.AI_BASE_URL ? (new URL(global.AI_BASE_URL)).hostname : '未設定';

                // 更新卡片列表
                const container = document.getElementById('accounts-container');
                if (accounts.length === 0) {{
                    container.innerHTML = `
                        <div class="col-span-full bg-gray-900 border border-gray-800 rounded-2xl p-12 text-center space-y-3">
                            <span class="text-4xl block">🏢</span>
                            <h3 class="text-base font-bold text-gray-200">目前尚無任何社群帳號工作台</h3>
                            <p class="text-xs text-gray-400">點擊上方「➕ 新增社群帳號工作台」，輸入帳號 Cookie 即可立刻建立專屬發文工作台！</p>
                            <button onclick="openAddAccountModal()" class="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-xl text-xs font-bold transition">
                                立即建立第一個工作台
                            </button>
                        </div>
                    `;
                    return;
                }}

                container.innerHTML = accounts.map(acc => renderAccountCard(acc)).join('');
            }}

            function renderAccountCard(acc) {{
                const isRunning = acc.status && acc.status.state === 'RUNNING';
                const isFailed = acc.status && acc.status.state === 'FAILED';
                const isSuccess = acc.status && acc.status.state === 'SUCCESS';
                const hasSession = acc.has_session;

                let stateBadge = `<span class="text-[10px] px-2 py-0.5 rounded-full bg-gray-800 text-gray-400 border border-gray-700">待命中</span>`;
                if (isRunning) {{
                    stateBadge = `<span class="text-[10px] px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-400 border border-indigo-700 animate-pulse">⏳ 發布中...</span>`;
                }} else if (isSuccess) {{
                    stateBadge = `<span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-700">✅ 最近發布成功</span>`;
                }} else if (isFailed) {{
                    stateBadge = `<span class="text-[10px] px-2 py-0.5 rounded-full bg-red-950 text-red-400 border border-red-700">❌ 執行失敗</span>`;
                }}

                const sessionBadge = hasSession 
                    ? `<span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800">✅ Session 已就緒</span>`
                    : `<span class="text-[10px] px-2 py-0.5 rounded-full bg-red-950 text-red-400 border border-red-800">⚠️ 缺少 Session</span>`;

                return `
                    <div class="bg-gray-900 border ${{isFailed ? 'border-red-900/60 shadow-lg shadow-red-950/20' : (isRunning ? 'border-indigo-600 shadow-lg shadow-indigo-950/30' : 'border-gray-800')}} rounded-2xl p-5 space-y-4 transition-all">
                        <!-- 卡片頂部 -->
                        <div class="flex items-start justify-between gap-3 border-b border-gray-800/80 pb-3">
                            <div class="flex items-center gap-2.5">
                                <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-700 to-purple-600 flex items-center justify-center font-bold text-white text-sm shadow-md">
                                    ${{acc.name.charAt(0).toUpperCase()}}
                                </div>
                                <div>
                                    <h3 class="text-sm font-bold text-white flex items-center gap-1.5">
                                        <span>${{escapeHtml(acc.name)}}</span>
                                    </h3>
                                    <div class="flex items-center gap-2 mt-1">
                                        <span class="text-[10px] text-gray-400">ID: <code class="text-gray-300">${{acc.id}}</code></span>
                                        <span class="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-indigo-300 font-medium">${{acc.target_region}}</span>
                                    </div>
                                </div>
                            </div>
                            <div class="flex items-center gap-2">
                                <button onclick="toggleAccount('${{acc.id}}')" class="text-xs px-2.5 py-1 rounded-lg font-medium transition ${{acc.enabled ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-gray-800 text-gray-400'}}">
                                    ${{acc.enabled ? '啟用中' : '已暫停'}}
                                </button>
                            </div>
                        </div>

                        <!-- 參數詳細資訊 -->
                        <div class="grid grid-cols-2 gap-2.5 text-xs text-gray-300 bg-gray-950/60 p-3 rounded-xl border border-gray-800/60">
                            <div>
                                <span class="text-gray-500 block text-[11px]">特定遊戲名稱</span>
                                <span class="font-medium text-white truncate block mt-0.5">${{escapeHtml(acc.game_name)}}</span>
                            </div>
                            <div>
                                <span class="text-gray-500 block text-[11px]">監控板塊 (Subreddit)</span>
                                <span class="font-medium text-white block mt-0.5">r/${{escapeHtml(acc.subreddit)}} (≥${{acc.min_upvotes}}讚)</span>
                            </div>
                            <div class="col-span-2 flex items-center justify-between pt-1 border-t border-gray-800/40">
                                <div class="flex items-center gap-2">
                                    ${{sessionBadge}}
                                    ${{stateBadge}}
                                </div>
                                <span class="text-[10px] text-gray-500">${{acc.status?.timestamp || ''}}</span>
                            </div>
                        </div>

                        <!-- 即時進度動態條 (若正在執行) -->
                        ${{isRunning ? `
                            <div class="bg-indigo-950/40 border border-indigo-800/60 p-2.5 rounded-xl flex items-center gap-2.5 text-xs text-indigo-200">
                                <div class="animate-spin rounded-full h-4 w-4 border-2 border-indigo-400 border-t-transparent"></div>
                                <span class="font-medium truncate">${{acc.status.step}}: ${{acc.status.message}}</span>
                            </div>
                        ` : ''}}

                        <!-- 錯誤診斷區塊 (若出錯) -->
                        ${{isFailed ? `
                            <div class="bg-red-950/30 border border-red-800/60 p-3 rounded-xl space-y-2 text-xs">
                                <div class="flex items-center justify-between">
                                    <span class="text-red-400 font-bold flex items-center gap-1">
                                        <span>🚨 錯誤階段：${{acc.error.failed_step || '未知'}}</span>
                                    </span>
                                    <button onclick="copyText('${{escapeForJs(acc.error.traceback)}}', this)" class="bg-red-900/60 hover:bg-red-800 text-red-200 px-2 py-0.5 rounded text-[10px] transition">
                                        📋 複製錯誤日誌
                                    </button>
                                </div>
                                <pre class="text-red-300/90 text-[11px] font-mono whitespace-pre-wrap max-h-24 overflow-y-auto">${{escapeHtml(acc.error.error_message)}}</pre>
                            </div>
                        ` : ''}}

                        <!-- 卡片底部動作按鈕 -->
                        <div class="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-gray-800/80">
                            <div class="flex items-center gap-2">
                                <button onclick="triggerAccount('${{acc.id}}')" ${{isRunning ? 'disabled' : ''}} class="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-3.5 py-1.5 rounded-lg text-xs font-bold transition shadow-sm flex items-center gap-1">
                                    <span>⚡ 點火此帳號</span>
                                </button>
                                <button onclick="copyAccountSession('${{acc.id}}', this)" class="bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 px-2.5 py-1.5 rounded-lg text-xs transition">
                                    <span>📋 複製 Session</span>
                                </button>
                            </div>
                            <div class="flex items-center gap-1.5">
                                <button onclick="openEditAccountModal('${{acc.id}}')" class="text-gray-400 hover:text-white px-2 py-1 text-xs">
                                    <span>⚙️ 編輯</span>
                                </button>
                                <button onclick="deleteAccount('${{acc.id}}', '${{escapeForJs(acc.name)}}')" class="text-red-400 hover:text-red-300 px-2 py-1 text-xs">
                                    <span>🗑️ 刪除</span>
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            }}

            // 工具函式
            function escapeHtml(str) {{
                if (!str) return '';
                return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
            }}
            function escapeForJs(str) {{
                if (!str) return '';
                return encodeURIComponent(str);
            }}

            function copyText(encodedStr, btn) {{
                const decoded = decodeURIComponent(encodedStr);
                navigator.clipboard.writeText(decoded).then(() => {{
                    const orig = btn.innerText;
                    btn.innerText = '✅ 已複製！';
                    setTimeout(() => {{ btn.innerText = orig; }}, 2000);
                }});
            }}

            async function copyAccountSession(accId, btn) {{
                try {{
                    const res = await fetch(`/api/accounts/${{accId}}/session`);
                    const data = await res.json();
                    if (data.session) {{
                        navigator.clipboard.writeText(data.session).then(() => {{
                            const orig = btn.innerText;
                            btn.innerText = '✅ Session 已複製！';
                            setTimeout(() => {{ btn.innerText = orig; }}, 2000);
                        }});
                    }} else {{
                        alert("此帳號尚未設定 Session Cookie！");
                    }}
                }} catch (e) {{
                    alert("獲取 Session 失敗: " + e);
                }}
            }}

            // Modal 操作
            function populateRegionsSelect(selectedVal) {{
                const sel = document.getElementById('acc-region');
                sel.innerHTML = AVAILABLE_REGIONS.map(r => `
                    <option value="${{r}}" ${{r === selectedVal ? 'selected' : ''}}>${{r}}</option>
                `).join('');
            }}

            function openAddAccountModal() {{
                document.getElementById('modal-account-title').innerText = '➕ 新增社群帳號工作台';
                document.getElementById('acc-id').value = '';
                document.getElementById('acc-name').value = '';
                document.getElementById('acc-game').value = '';
                document.getElementById('acc-subreddit').value = '';
                document.getElementById('acc-upvotes').value = '100';
                document.getElementById('acc-session').value = '';
                document.getElementById('acc-enabled').checked = true;
                populateRegionsSelect("台灣 (繁體中文)");
                document.getElementById('modal-account').classList.remove('hidden');
            }}

            function openEditAccountModal(accId) {{
                const acc = (currentData?.accounts || []).find(a => a.id === accId);
                if (!acc) return;

                document.getElementById('modal-account-title').innerText = '⚙️ 編輯社群帳號工作台';
                document.getElementById('acc-id').value = acc.id;
                document.getElementById('acc-name').value = acc.name || '';
                document.getElementById('acc-game').value = acc.game_name || '';
                document.getElementById('acc-subreddit').value = acc.subreddit || '';
                document.getElementById('acc-upvotes').value = acc.min_upvotes || '100';
                document.getElementById('acc-enabled').checked = acc.enabled !== false;
                populateRegionsSelect(acc.target_region || "台灣 (繁體中文)");

                // 異步填入現有 Session
                fetch(`/api/accounts/${{accId}}/session`).then(r => r.json()).then(d => {{
                    document.getElementById('acc-session').value = d.session || '';
                }});

                document.getElementById('modal-account').classList.remove('hidden');
            }}

            function closeAccountModal() {{
                document.getElementById('modal-account').classList.add('hidden');
            }}

            async function handleAccountFormSubmit(e) {{
                e.preventDefault();
                const form = document.getElementById('form-account');
                const formData = new FormData(form);
                const payload = {{
                    id: formData.get('id') || undefined,
                    name: formData.get('name'),
                    target_region: formData.get('target_region'),
                    game_name: formData.get('game_name'),
                    subreddit: formData.get('subreddit'),
                    min_upvotes: parseInt(formData.get('min_upvotes') || '100', 10),
                    enabled: formData.get('enabled') === 'on',
                    session_data: formData.get('session_data') || undefined
                }};

                try {{
                    const res = await fetch('/api/accounts/save', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(payload)
                    }});
                    const result = await res.json();
                    if (result.status === 'success') {{
                        closeAccountModal();
                        fetchDashboardData();
                    }}
                }} catch (err) {{
                    alert("儲存帳號失敗: " + err);
                }}
            }}

            async function toggleAccount(accId) {{
                await fetch(`/api/accounts/${{accId}}/toggle`, {{ method: 'POST' }});
                fetchDashboardData();
            }}

            async function deleteAccount(accId, rawName) {{
                const name = decodeURIComponent(rawName);
                if (confirm(`確定要刪除帳號工作台【${{name}}】嗎？\n此操作將刪除此帳號的專屬設定與 Session。`)) {{
                    await fetch(`/api/accounts/${{accId}}/delete`, {{ method: 'POST' }});
                    fetchDashboardData();
                }}
            }}

            async function triggerAccount(accId) {{
                await fetch(`/api/accounts/${{accId}}/trigger`, {{ method: 'POST' }});
                fetchDashboardData();
            }}

            async function triggerAllAccounts() {{
                if (confirm("確定要一鍵點火所有已啟用的帳號工作台嗎？\n系統將排隊依序執行每個帳號的搬運與發布任務。")) {{
                    await fetch('/api/trigger-all', {{ method: 'POST' }});
                    fetchDashboardData();
                }}
            }}

            // 全域設定 Modal
            function openGlobalSettingsModal() {{
                const g = currentData?.global_settings || {{}};
                document.getElementById('global-base-url').value = g.AI_BASE_URL || '';
                document.getElementById('global-api-key').value = g.AI_API_KEY || '';
                document.getElementById('global-model').value = g.AI_MODEL || 'gemini-2.5-flash';
                document.getElementById('modal-global-settings').classList.remove('hidden');
            }}

            function closeGlobalSettingsModal() {{
                document.getElementById('modal-global-settings').classList.add('hidden');
            }}

            async function handleGlobalSettingsSubmit(e) {{
                e.preventDefault();
                const payload = {{
                    AI_BASE_URL: document.getElementById('global-base-url').value.trim(),
                    AI_API_KEY: document.getElementById('global-api-key').value.trim(),
                    AI_MODEL: document.getElementById('global-model').value.trim()
                }};

                try {{
                    await fetch('/api/global-settings', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(payload)
                    }});
                    closeGlobalSettingsModal();
                    fetchDashboardData();
                    alert("全域 AI 設定已成功更新！");
                }} catch (err) {{
                    alert("儲存 AI 設定失敗: " + err);
                }}
            }}

            // 啟動與自動輪詢 (每 2.5 秒)
            fetchDashboardData();
            setInterval(fetchDashboardData, 2500);
        </script>
    </body>
    </html>
    """
    return html_content

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
