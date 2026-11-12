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

import asyncio
import account_manager

app = FastAPI(title="Threads 矩陣多帳號自動發布主控台")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(auto_scheduler_daemon())

async def auto_scheduler_daemon():
    """24/7 背景排程巡航守護進程：支援常規定時巡航與破裂級爆款自主提前插隊"""
    await asyncio.sleep(3)
    print("🕒 [Auto Scheduler] 24/7 自動巡航排程守護進程已啟動！")
    loop_count = 0
    while True:
        try:
            # 1. 常規排程檢測 (每 30 秒)
            due_accounts = account_manager.get_due_accounts()
            for acc in due_accounts:
                acc_id = acc["id"]
                acc_name = acc.get("name", acc_id)
                print(f"⏰ [Auto Scheduler] 帳號【{acc_name}】排程時間到 ({acc.get('next_run')})，常規自動點火！")
                account_manager.mark_account_run_completed(acc_id)
                env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
                subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "main.py"), "--account", acc_id], cwd=BASE_DIR, env=env)
                await asyncio.sleep(2)

            # 2. 破裂級爆款雷達插隊檢測 (每 15 分鐘 = 30次輪詢)
            loop_count += 1
            if loop_count >= 30:
                loop_count = 0
                all_accs = account_manager.get_accounts()
                for acc in all_accs:
                    if acc.get("enabled", True) and account_manager.is_fast_track_allowed(acc["id"]):
                        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
                        subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "main.py"), "--account", acc["id"], "--fast-track"], cwd=BASE_DIR, env=env)
                        await asyncio.sleep(2)

        except Exception as e:
            print(f"⚠️ [Auto Scheduler Error] {e}")
        await asyncio.sleep(30)

@app.get("/api/analytics")
async def get_analytics_api():
    """回傳矩陣營運情報簡報數據"""
    return JSONResponse(account_manager.get_analytics_summary())

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

@app.get("/api/global-cookies")
async def get_global_cookies_api():
    return JSONResponse({
        "x": account_manager.get_global_cookie("x"),
        "facebook_scraper": account_manager.get_global_cookie("facebook_scraper")
    })

@app.post("/api/global-cookies/save")
async def save_global_cookie_api(request: Request):
    data = await request.json()
    platform = data.get("platform")
    cookie_data = data.get("cookie_data", "")
    if platform in ["x", "facebook_scraper"]:
        account_manager.save_global_cookie(platform, cookie_data)
        plat_label = "X (Twitter)" if platform == "x" else "Facebook 爬文"
        return JSONResponse({"status": "success", "message": f"{plat_label} 爬蟲 Cookie 已成功儲存！"})
    return JSONResponse({"status": "error", "message": "未知的平台代碼"}, status_code=400)

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

@app.get("/api/accounts/{acc_id}/milestones")
async def get_milestones_api(acc_id: str):
    """獲取指定帳號的重大事件日曆、當前戰役狀態與 AI 探測候選"""
    milestones = account_manager.get_account_milestones(acc_id)
    campaign_status = account_manager.get_account_campaign_status(acc_id)
    discovered = account_manager.get_discovered_milestones(acc_id)
    return JSONResponse({
        "milestones": milestones,
        "campaign_status": campaign_status,
        "discovered": discovered
    })

@app.post("/api/accounts/{acc_id}/milestones/save")
async def save_milestone_api(acc_id: str, request: Request):
    data = await request.json()
    saved = account_manager.add_or_update_milestone(acc_id, data)
    return JSONResponse({"status": "success", "milestone": saved})

@app.post("/api/accounts/{acc_id}/milestones/delete")
async def delete_milestone_api(acc_id: str, request: Request):
    data = await request.json()
    m_id = data.get("id")
    if m_id:
        account_manager.delete_milestone(acc_id, m_id)
    return JSONResponse({"status": "success"})

@app.post("/api/accounts/{acc_id}/milestones/approve-discovered")
async def approve_discovered_api(acc_id: str, request: Request):
    data = await request.json()
    disc_id = data.get("id")
    if disc_id:
        success = account_manager.approve_discovered_milestone(acc_id, disc_id)
        return JSONResponse({"status": "success" if success else "error"})
    return JSONResponse({"status": "error", "message": "缺少事件 ID"}, status_code=400)

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
                        🚀 Threads & Facebook 跨平台矩陣搬運主控台
                    </h1>
                    <p class="text-xs text-gray-400 mt-1">
                        跨平台資訊差自動發掘 ‧ 發現時間縮短至 1~2 小時潛力爆文 ‧ 100% 格式語氣照抄在地化 ‧ 零作者標註
                    </p>
                </div>
                <div class="flex flex-wrap items-center gap-2.5">
                    <button onclick="openAnalyticsModal()" class="bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white px-3.5 py-2 rounded-xl text-xs font-bold transition shadow-lg shadow-amber-600/30 flex items-center gap-1.5">
                        <span>📊 矩陣營運情報簡報</span>
                    </button>
                    <button onclick="openGlobalCookiesModal()" class="bg-gradient-to-r from-sky-600 to-blue-600 hover:from-sky-500 hover:to-blue-500 text-white px-3.5 py-2 rounded-xl text-xs font-bold transition shadow-lg shadow-sky-600/30 flex items-center gap-1.5">
                        <span>🔑 爬蟲授權管理 (X / FB 爬文)</span>
                    </button>
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
                    <span class="text-xs text-gray-400 block">24/7 自動排程巡航</span>
                    <span id="stat-scheduler" class="text-xs font-semibold text-emerald-400 mt-2 block truncate flex items-center gap-1.5">
                        <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"></span>
                        <span>🟢 守護巡航中</span>
                    </span>
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
                        <input id="acc-name" name="name" required placeholder="例如：@my_threads_tw 或 FB遊戲粉絲團" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none">
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-gray-300 font-medium mb-1">🎯 目標發布社群 (Target Platform)*</label>
                            <select id="acc-target-platform" name="target_platform" onchange="handleTargetPlatformChange()" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none">
                                <option value="Threads">🧵 Threads (台灣/全球高速擴散)</option>
                                <option value="Facebook">📘 Facebook (粉專/社團廣泛受眾)</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-gray-300 font-medium mb-1">📡 來源監控雷達（可複選多平台並行監控）*</label>
                            <div class="flex flex-wrap gap-2 pt-1">
                                <label class="flex items-center gap-1.5 bg-gray-950 border border-gray-800 px-2 py-1.5 rounded-lg cursor-pointer hover:border-gray-700">
                                    <input type="checkbox" name="source_platforms" value="巴哈姆特" id="src-baha" class="rounded bg-gray-900 border-gray-700 text-indigo-500">
                                    <span class="text-[11px]">巴哈姆特</span>
                                </label>
                                <label class="flex items-center gap-1.5 bg-gray-950 border border-gray-800 px-2 py-1.5 rounded-lg cursor-pointer hover:border-gray-700">
                                    <input type="checkbox" name="source_platforms" value="Reddit" id="src-reddit" class="rounded bg-gray-900 border-gray-700 text-indigo-500">
                                    <span class="text-[11px]">Reddit</span>
                                </label>
                                <label class="flex items-center gap-1.5 bg-gray-950 border border-gray-800 px-2 py-1.5 rounded-lg cursor-pointer hover:border-gray-700">
                                    <input type="checkbox" name="source_platforms" value="X" id="src-x" class="rounded bg-gray-900 border-gray-700 text-indigo-500">
                                    <span class="text-[11px]">𝕏 (Twitter)</span>
                                </label>
                                <label class="flex items-center gap-1.5 bg-gray-950 border border-gray-800 px-2 py-1.5 rounded-lg cursor-pointer hover:border-gray-700">
                                    <input type="checkbox" name="source_platforms" value="Twitch" id="src-twitch" class="rounded bg-gray-900 border-gray-700 text-indigo-500">
                                    <span class="text-[11px] text-purple-300">🟣 Twitch (短片)</span>
                                </label>
                                <label id="lbl-source-threads" class="hidden items-center gap-1.5 bg-gray-950 border border-gray-800 px-2 py-1.5 rounded-lg cursor-pointer hover:border-gray-700">
                                    <input type="checkbox" name="source_platforms" value="Threads" id="src-threads" class="rounded bg-gray-900 border-gray-700 text-indigo-500">
                                    <span class="text-[11px]">Threads</span>
                                </label>
                            </div>
                        </div>
                    </div>

                    <div>
                        <div class="flex items-center justify-between mb-1">
                            <label class="block text-gray-300 font-medium">🎯 獨立 Agent 成長策略與選材使命 (Prompt)*</label>
                            <span class="text-indigo-400 text-[10px]">✨ AI 依此標準在多平台候選文中評選最有料爆款</span>
                        </div>
                        <textarea id="acc-strategy" name="strategy_prompt" rows="2" placeholder="例如：目標是在該領域吸引最多粉絲關注，優先挑選最有料、最好笑的迷因圖文與即時情報，避開生硬的文字公告。" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-xs text-gray-100 focus:border-indigo-500 focus:outline-none"></textarea>
                    </div>

                    <div class="bg-gray-950/70 border border-gray-800 p-3 rounded-xl space-y-2.5">
                        <label class="block text-gray-300 font-medium">⏰ 24/7 自動排程巡航發布模式</label>
                        <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
                            <label class="flex items-center gap-1.5 bg-gray-900 p-2 rounded-lg border border-gray-800 cursor-pointer text-gray-300">
                                <input type="radio" name="schedule_type" value="fixed_times" id="sched-fixed" onchange="updateScheduleFields()" class="text-indigo-500">
                                <span>黃金時段定點</span>
                            </label>
                            <label class="flex items-center gap-1.5 bg-gray-900 p-2 rounded-lg border border-gray-800 cursor-pointer text-gray-300">
                                <input type="radio" name="schedule_type" value="interval" id="sched-interval" onchange="updateScheduleFields()" class="text-indigo-500" checked>
                                <span>固定週期巡航</span>
                            </label>
                            <label class="flex items-center gap-1.5 bg-gray-900 p-2 rounded-lg border border-gray-800 cursor-pointer text-gray-300">
                                <input type="radio" name="schedule_type" value="manual" id="sched-manual" onchange="updateScheduleFields()" class="text-indigo-500">
                                <span>僅手動點火</span>
                            </label>
                        </div>
                        <div id="sched-fixed-box" class="hidden">
                            <label class="text-[11px] text-gray-400 block mb-1">每日發布時間點 (逗號分隔，24小時制)：</label>
                            <input id="acc-fixed-times" name="fixed_times" value="12:30, 18:30, 22:00" placeholder="例如：12:30, 18:30, 22:00" class="w-full bg-gray-900 border border-gray-700 rounded-lg p-2 text-xs font-mono text-gray-200">
                        </div>
                        <div id="sched-interval-box">
                            <label class="text-[11px] text-gray-400 block mb-1">巡航間隔時間 (分鐘)：</label>
                            <input type="number" id="acc-interval-minutes" name="interval_minutes" value="180" min="30" class="w-full bg-gray-900 border border-gray-700 rounded-lg p-2 text-xs font-mono text-gray-200">
                        </div>
                    </div>

                    <!-- 破裂級爆款自主插隊設定 -->
                    <div class="bg-amber-950/20 border border-amber-900/40 p-3 rounded-xl space-y-2.5">
                        <div class="flex items-center justify-between">
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="checkbox" id="acc-enable-fast-track" name="enable_fast_track" class="rounded bg-gray-950 border-gray-700 text-amber-500 focus:ring-0" checked>
                                <span class="text-xs font-bold text-amber-300">🚨 破裂級爆款自主插隊 (搶吃第一波流量紅利)</span>
                            </label>
                            <span class="text-[10px] text-amber-400/80">打破常規排程提前點火</span>
                        </div>
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                            <div>
                                <label class="block text-gray-400 text-[11px] mb-1">觸發爆款門檻 (讚數 / Likes)*</label>
                                <input type="number" id="acc-fast-track-min-upvotes" name="fast_track_min_upvotes" value="300" class="w-full bg-gray-900 border border-gray-700 rounded-lg p-2 text-xs font-mono text-gray-200">
                            </div>
                            <div>
                                <label class="block text-gray-400 text-[11px] mb-1">最低安全冷卻間隔 (防封號保護)*</label>
                                <div class="flex items-center gap-1.5">
                                    <input type="number" id="acc-cooldown-minutes" name="cooldown_minutes" value="45" min="15" class="w-full bg-gray-900 border border-gray-700 rounded-lg p-2 text-xs font-mono text-gray-200">
                                    <span class="text-xs text-gray-400 whitespace-nowrap">分鐘</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-gray-300 font-medium mb-1">⏱️ 發現時效模式 (Discovery Latency)*</label>
                            <select id="acc-discovery-mode" name="discovery_mode" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none">
                                <option value="rising">⚡ 剛爆發潛力榜 (Rising - 發現時間最短，約 1~2 小時)</option>
                                <option value="hot">🔥 成熟熱門榜 (Hot - 經典高讚熱門)</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-gray-300 font-medium mb-1">目標地區與語言 (受眾)*</label>
                            <select id="acc-region" name="target_region" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none">
                                <!-- 動態填入地區 -->
                            </select>
                        </div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-gray-300 font-medium mb-1">特定遊戲名稱 (專有名詞對齊)*</label>
                            <input id="acc-game" name="game_name" required placeholder="例如：Monster Hunter Wilds / 原神" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none">
                        </div>
                        <div>
                            <label class="block text-gray-300 font-medium mb-1">監控板塊 / 關鍵字 (Subreddit)*</label>
                            <input id="acc-subreddit" name="subreddit" required placeholder="例如：MonsterHunter" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none">
                        </div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-gray-300 font-medium mb-1">最低熱門讚數 (Min Likes/Upvotes)*</label>
                            <input type="number" id="acc-upvotes" name="min_upvotes" required value="100" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none">
                        </div>
                        <div>
                            <div class="flex items-center justify-between mb-1">
                                <label class="block text-gray-300 font-medium">🏷️ 爆款主題標籤 (Hashtags)</label>
                                <span class="text-indigo-400 text-[10px]">✨ 提升演算法推播</span>
                            </div>
                            <input id="acc-tags" name="custom_tags" placeholder="例如：#魔物獵人旅人 (留空AI自動生成)" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none">
                        </div>
                    </div>

                    <div>
                        <div class="flex items-center justify-between mb-1">
                            <label id="label-session-cookie" class="text-gray-300 font-medium">🎯 該帳號專屬【發布貼文】Cookie Session (JSON)</label>
                            <div class="flex items-center gap-2">
                                <span id="hint-session-tool" class="text-gray-500 text-[10px]">支援 Cookie-Editor 陣列或 Playwright 格式</span>
                                <button type="button" onclick="pasteToElement('acc-session')" class="text-[10px] bg-indigo-900/60 hover:bg-indigo-700 text-indigo-200 px-2 py-0.5 rounded border border-indigo-500/40 transition">📋 一鍵從剪貼簿貼上</button>
                            </div>
                        </div>
                        <textarea id="acc-session" name="session_data" rows="3" placeholder='貼上 Cookie-Editor 匯出的 JSON 陣列 [...] 或 Playwright 格式 {{"cookies": [...]}}' class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2 text-xs font-mono text-gray-300 focus:border-amber-500 focus:outline-none"></textarea>
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

        <!-- =================== Modal 3: 全局來源爬蟲 Cookie 管理 =================== -->
        <div id="modal-global-cookies" class="hidden fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div class="bg-gray-900 border border-gray-700 w-full max-w-2xl rounded-2xl p-6 shadow-2xl space-y-5 max-h-[90vh] overflow-y-auto">
                <div class="flex items-center justify-between border-b border-gray-800 pb-3">
                    <h3 class="text-base font-bold text-white flex items-center gap-2">
                        <span>🔑 全局來源爬蟲 Cookie 管理 (X / FB 爬文)</span>
                    </h3>
                    <button onclick="closeGlobalCookiesModal()" class="text-gray-400 hover:text-white text-lg font-mono">&times;</button>
                </div>

                <div class="bg-blue-950/40 border border-blue-900/50 p-3 rounded-xl text-xs text-blue-200 leading-relaxed">
                    💡 <strong>爬蟲 Cookie 分流機制</strong>：
                    當工作台需要從 <strong>X (Twitter)</strong> 或 <strong>Facebook (社團/粉專)</strong> 爬取即時爆文時，使用此處設定的憑證。<br>
                    支援 <strong>Cookie-Editor 匯出的 JSON 陣列</strong> (<code>[...]</code>) 或 Playwright 格式，系統將<strong>自動識別轉換</strong>！
                </div>

                <!-- X (Twitter) 爬蟲 Cookie -->
                <div class="bg-gray-950/80 border border-gray-800 p-4 rounded-xl space-y-3">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-2">
                            <span class="text-sm font-bold text-sky-400 flex items-center gap-1.5">
                                <span>𝕏</span> X (Twitter) 爬蟲 Cookie
                            </span>
                            <span id="badge-x-cookie-status" class="text-[10px] px-2 py-0.5 rounded-full bg-gray-800 text-gray-400 border border-gray-700">檢測中...</span>
                        </div>
                        <button type="button" onclick="pasteToElement('global-x-cookie')" class="text-xs bg-sky-950/80 hover:bg-sky-800 text-sky-300 px-2.5 py-1 rounded-lg border border-sky-700/50 transition">📋 一鍵從剪貼簿貼上</button>
                    </div>
                    <textarea id="global-x-cookie" rows="3" placeholder='在此貼上 X 的 Cookie（Cookie-Editor JSON 陣列或 Playwright 格式）...' class="w-full bg-gray-900 border border-gray-700 rounded-lg p-2.5 text-xs font-mono text-gray-300 focus:border-sky-500 focus:outline-none"></textarea>
                    <div class="flex justify-end">
                        <button type="button" onclick="saveGlobalCookie('x')" class="px-4 py-1.5 bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold rounded-lg transition shadow-md shadow-sky-900/30">💾 儲存 X 爬蟲 Cookie</button>
                    </div>
                </div>

                <!-- Facebook 爬文專用 Cookie -->
                <div class="bg-gray-950/80 border border-gray-800 p-4 rounded-xl space-y-3">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-2">
                            <span class="text-sm font-bold text-blue-400 flex items-center gap-1.5">
                                <span>📘</span> Facebook 爬文專用 Cookie
                            </span>
                            <span id="badge-fb-cookie-status" class="text-[10px] px-2 py-0.5 rounded-full bg-gray-800 text-gray-400 border border-gray-700">檢測中...</span>
                        </div>
                        <button type="button" onclick="pasteToElement('global-fb-scraper-cookie')" class="text-xs bg-blue-950/80 hover:bg-blue-800 text-blue-300 px-2.5 py-1 rounded-lg border border-blue-700/50 transition">📋 一鍵從剪貼簿貼上</button>
                    </div>
                    <p class="text-[11px] text-gray-500">
                        🛡️ 建議使用專門用來看文/爬文的 Facebook 小號 Cookie，與主要發文的 Facebook 帳號徹底分流，確保發文主號安全。
                    </p>
                    <textarea id="global-fb-scraper-cookie" rows="3" placeholder='在此貼上 Facebook 爬文小號的 Cookie...' class="w-full bg-gray-900 border border-gray-700 rounded-lg p-2.5 text-xs font-mono text-gray-300 focus:border-blue-500 focus:outline-none"></textarea>
                    <div class="flex justify-end">
                        <button type="button" onclick="saveGlobalCookie('facebook_scraper')" class="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold rounded-lg transition shadow-md shadow-blue-900/30">💾 儲存 FB 爬文 Cookie</button>
                    </div>
                </div>

                <div class="flex justify-end pt-2 border-t border-gray-800">
                    <button type="button" onclick="closeGlobalCookiesModal()" class="px-5 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 font-medium text-xs">關閉視窗</button>
                </div>
            </div>
        </div>

        <!-- =================== Modal 4: 矩陣營運情報與 AI 決策簡報 =================== -->
        <div id="modal-analytics" class="hidden fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div class="bg-gray-900 border border-gray-700 w-full max-w-4xl rounded-2xl p-6 shadow-2xl space-y-5 max-h-[90vh] overflow-y-auto">
                <div class="flex items-center justify-between border-b border-gray-800 pb-3">
                    <h3 class="text-base font-bold text-white flex items-center gap-2">
                        <span>📊 跨社群矩陣營運情報與 AI 決策簡報</span>
                    </h3>
                    <button onclick="closeAnalyticsModal()" class="text-gray-400 hover:text-white text-lg font-mono">&times;</button>
                </div>

                <!-- 關鍵指標卡片 -->
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div class="bg-gray-950/80 border border-gray-800 p-3.5 rounded-xl">
                        <span class="text-[11px] text-gray-400 block">全矩陣搬運總篇數</span>
                        <span id="analytics-total-posts" class="text-2xl font-bold text-white mt-1 block">0</span>
                    </div>
                    <div class="bg-gray-950/80 border border-amber-900/40 p-3.5 rounded-xl">
                        <span class="text-[11px] text-amber-300 block">🚨 破裂爆款自主插隊</span>
                        <span id="analytics-fast-track-count" class="text-2xl font-bold text-amber-400 mt-1 block">0</span>
                    </div>
                    <div class="bg-gray-950/80 border border-gray-800 p-3.5 rounded-xl">
                        <span class="text-[11px] text-gray-400 block">情報來源分佈</span>
                        <div id="analytics-sources-breakdown" class="flex flex-wrap gap-1 mt-1.5 text-[11px]">--</div>
                    </div>
                    <div class="bg-gray-950/80 border border-gray-800 p-3.5 rounded-xl">
                        <span class="text-[11px] text-gray-400 block">24H 活躍時段</span>
                        <span id="analytics-peak-hour" class="text-xs font-mono font-bold text-indigo-300 mt-2 block">統計中...</span>
                    </div>
                </div>

                <!-- AI 選材決策與發布紀錄明細 -->
                <div class="space-y-2.5">
                    <div class="flex items-center justify-between">
                        <h4 class="text-xs font-bold text-gray-300 flex items-center gap-1.5">
                            <span>🧠 最近 AI 選材與發布決策紀錄 (最新 20 筆)</span>
                        </h4>
                        <span class="text-[10px] text-gray-500">透明回溯 AI 評選理由與各來源熱度</span>
                    </div>

                    <div class="overflow-x-auto rounded-xl border border-gray-800">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-gray-950 text-gray-400 text-[11px] border-b border-gray-800">
                                <tr>
                                    <th class="p-2.5 font-medium">時間</th>
                                    <th class="p-2.5 font-medium">帳號工作台</th>
                                    <th class="p-2.5 font-medium">來源平台</th>
                                    <th class="p-2.5 font-medium">候選貼文標題 / 讚數</th>
                                    <th class="p-2.5 font-medium">發布模式</th>
                                    <th class="p-2.5 font-medium">🎯 AI 選材決策理由</th>
                                </tr>
                            </thead>
                            <tbody id="analytics-table-body" class="divide-y divide-gray-800 text-gray-300 text-[11px]">
                                <tr>
                                    <td colspan="6" class="p-6 text-center text-gray-500">尚無營運數據記錄</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="flex justify-end pt-2 border-t border-gray-800">
                    <button type="button" onclick="closeAnalyticsModal()" class="px-5 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 font-medium text-xs">關閉情報簡報</button>
                </div>
            </div>
        </div>

        <!-- =================== Modal 5: 未來重大事件日曆與戰役模式 =================== -->
        <div id="modal-milestones" class="hidden fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div class="bg-gray-900 border border-gray-700 w-full max-w-3xl rounded-2xl p-6 shadow-2xl space-y-5 max-h-[90vh] overflow-y-auto">
                <div class="flex items-center justify-between border-b border-gray-800 pb-3">
                    <div class="flex items-center gap-2">
                        <span class="text-xl">📅</span>
                        <div>
                            <h3 id="milestones-modal-acc-title" class="text-base font-bold text-white flex items-center gap-2">
                                <span>作戰行事曆與重大事件 (Milestones)</span>
                            </h3>
                            <p class="text-[11px] text-gray-400">超前佈署重大發售日、測試、更新；AI 依據倒數天數自主切換「預熱 $\to$ 引爆 $\to$ 餘波」選材策略</p>
                        </div>
                    </div>
                    <button onclick="closeMilestonesModal()" class="text-gray-400 hover:text-white text-lg font-mono">&times;</button>
                </div>

                <!-- 當前活躍戰役狀態 Banner -->
                <div id="milestones-active-banner" class="p-3.5 rounded-xl border flex items-center justify-between text-xs">
                    <!-- 動態渲染 -->
                </div>

                <!-- 已安排的重大事件清單 -->
                <div class="space-y-3">
                    <div class="flex items-center justify-between">
                        <h4 class="text-xs font-bold text-gray-200 flex items-center gap-1.5">
                            <span>🎯 現有戰役事件清單</span>
                        </h4>
                        <span class="text-[10px] text-gray-500">按目標日期排序</span>
                    </div>
                    <div id="milestones-list-container" class="space-y-2">
                        <!-- 動態渲染事件卡片 -->
                    </div>
                </div>

                <!-- AI 自動探測到的未來大事候選 (一葉知秋) -->
                <div id="milestones-discovered-box" class="space-y-2.5 pt-2 border-t border-gray-800/80">
                    <div class="flex items-center justify-between">
                        <h4 class="text-xs font-bold text-purple-300 flex items-center gap-1.5">
                            <span>✨ AI 貼文雷達探測到之未來大事線索 (一葉知秋)</span>
                        </h4>
                        <span class="text-[10px] text-purple-400/80">自動從 X / Reddit / 媒體推文中嗅探到的時間點</span>
                    </div>
                    <div id="milestones-discovered-container" class="space-y-2">
                        <div class="text-xs text-gray-500 p-3 bg-gray-950/60 rounded-xl border border-gray-800 text-center">
                            目前尚未探測到新的未確認事件線索。當來源雷達抓到包含發售日/公測日爆文時將自動在此推薦！
                        </div>
                    </div>
                </div>

                <!-- 新增重大事件表單 -->
                <div class="bg-gray-950/80 border border-gray-800 p-4 rounded-xl space-y-3 text-xs">
                    <h4 class="font-bold text-white flex items-center gap-1.5">
                        <span>➕ 手動加入未來重大事件 (如 GTA6 上市 / DLC 公開測試)</span>
                    </h4>
                    <form id="form-new-milestone" onsubmit="handleNewMilestoneSubmit(event)" class="space-y-3">
                        <input type="hidden" id="mile-acc-id" value="">
                        <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                            <div class="sm:col-span-2">
                                <label class="block text-gray-400 text-[11px] mb-1">事件名稱 / 旗艦大作主題*</label>
                                <input id="mile-title" required placeholder="例如：《GTA 6》PS平台預載與全球上市" class="w-full bg-gray-900 border border-gray-700 rounded-lg p-2 text-xs text-gray-100 focus:border-amber-500 focus:outline-none">
                            </div>
                            <div>
                                <label class="block text-gray-400 text-[11px] mb-1">目標發生日期 (YYYY-MM-DD)*</label>
                                <input type="date" id="mile-target-date" required class="w-full bg-gray-900 border border-gray-700 rounded-lg p-2 text-xs text-gray-100 focus:border-amber-500 focus:outline-none">
                            </div>
                        </div>
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                            <div>
                                <label class="block text-gray-400 text-[11px] mb-1">關聯關鍵字 (逗號分隔)</label>
                                <input id="mile-keywords" placeholder="例如：GTA, GTA6, Rockstar, PlayStation" class="w-full bg-gray-900 border border-gray-700 rounded-lg p-2 text-xs text-gray-100 focus:border-amber-500 focus:outline-none">
                            </div>
                            <div>
                                <label class="block text-gray-400 text-[11px] mb-1">事件備註 / 期望流量方向</label>
                                <input id="mile-notes" placeholder="例如：全球矚目超級大作，提前一週瘋狂搬運規格與捏臉" class="w-full bg-gray-900 border border-gray-700 rounded-lg p-2 text-xs text-gray-100 focus:border-amber-500 focus:outline-none">
                            </div>
                        </div>
                        <div class="flex justify-end pt-1">
                            <button type="submit" class="bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white font-bold px-4 py-2 rounded-xl text-xs transition shadow-md shadow-amber-900/30">
                                📌 儲存並加入戰役行事曆
                            </button>
                        </div>
                    </form>
                </div>

                <div class="flex justify-end pt-2 border-t border-gray-800">
                    <button type="button" onclick="closeMilestonesModal()" class="px-5 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 font-medium text-xs">關閉視窗</button>
                </div>
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
                if (document.getElementById('stat-total')) document.getElementById('stat-total').innerText = accounts.length;
                if (document.getElementById('stat-enabled')) document.getElementById('stat-enabled').innerText = accounts.filter(a => a.enabled).length;
                if (document.getElementById('stat-model')) document.getElementById('stat-model').innerText = global.AI_MODEL || '未設定';
                if (document.getElementById('stat-relay')) document.getElementById('stat-relay').innerText = global.AI_BASE_URL ? (new URL(global.AI_BASE_URL)).hostname : '未設定';

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

                const isFacebook = (acc.target_platform || 'Threads').toLowerCase() === 'facebook';
                const platformBadge = isFacebook 
                    ? `<span class="text-[10px] px-2 py-0.5 rounded-full bg-blue-950 text-blue-300 border border-blue-800 font-bold flex items-center gap-1">📘 Facebook</span>`
                    : `<span class="text-[10px] px-2 py-0.5 rounded-full bg-purple-950 text-purple-300 border border-purple-800 font-bold flex items-center gap-1">🧵 Threads</span>`;

                const sources = acc.source_platforms || (acc.source_platform ? [acc.source_platform] : ['Reddit']);
                const sourcesBadge = sources.map(s => `<span class="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-sky-300 border border-gray-700">📡 ${{escapeHtml(s)}}</span>`).join(' ');

                let scheduleBadge = '';
                if (acc.schedule_type === 'manual') {{
                    scheduleBadge = `<span class="text-[10px] px-2 py-0.5 rounded-full bg-gray-800 text-gray-400 border border-gray-700">✋ 僅手動點火</span>`;
                }} else if (acc.next_run) {{
                    const diffMs = new Date(acc.next_run.replace(/-/g, '/')) - new Date();
                    const diffMins = Math.round(diffMs / 60000);
                    const timePart = acc.next_run.split(' ')[1] || acc.next_run;
                    const countdownDesc = diffMins > 0 ? `倒數 ${{diffMins}} 分鐘` : '即將自動發布';
                    scheduleBadge = `<span class="text-[10px] px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-700 font-semibold">⏰ 下次: ${{timePart}} (${{countdownDesc}})</span>`;
                }}

                let fastTrackBadge = '';
                if (acc.enable_fast_track !== false) {{
                    fastTrackBadge = `<span class="text-[10px] px-1.5 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-800/60 font-medium" title="若發現≥${{acc.fast_track_min_upvotes || 300}}讚爆款將自動插隊發布">⚡ 爆款插隊 (≥${{acc.fast_track_min_upvotes || 300}}讚)</span>`;
                }}

                const camp = acc.campaign_status || {{ phase: 'CRUISE', badge_text: '⚡ 常規巡航', badge_color: 'indigo' }};
                let campBadgeClass = 'bg-indigo-950/40 text-indigo-300 border-indigo-800/40';
                if (camp.phase === 'WARMUP') {{
                    campBadgeClass = 'bg-amber-950/70 text-amber-300 border-amber-600/80 animate-pulse font-bold';
                }} else if (camp.phase === 'LAUNCH_DAY') {{
                    campBadgeClass = 'bg-red-950/70 text-red-300 border-red-500 font-extrabold animate-bounce';
                }} else if (camp.phase === 'AFTERMATH') {{
                    campBadgeClass = 'bg-emerald-950/60 text-emerald-300 border-emerald-600/80 font-semibold';
                }} else if (camp.badge_color === 'sky') {{
                    campBadgeClass = 'bg-sky-950/50 text-sky-300 border-sky-800/60 font-medium';
                }}
                const campaignBanner = `
                    <div class="flex items-center justify-between text-[11px] px-3 py-1.5 rounded-xl border ${{campBadgeClass}}">
                        <span class="flex items-center gap-1.5">${{escapeHtml(camp.badge_text)}}</span>
                        <button onclick="openMilestonesModal('${{acc.id}}')" class="text-[10px] text-gray-400 hover:text-white underline cursor-pointer">📅 大事記</button>
                    </div>
                `;

                return `
                    <div class="bg-gray-900 border ${{isFailed ? 'border-red-900/60 shadow-lg shadow-red-950/20' : (isRunning ? 'border-indigo-600 shadow-lg shadow-indigo-950/30' : 'border-gray-800')}} rounded-2xl p-5 space-y-4 transition-all">
                        <!-- 卡片頂部 -->
                        <div class="flex items-start justify-between gap-3 border-b border-gray-800/80 pb-3">
                            <div class="flex items-center gap-2.5">
                                <div class="w-9 h-9 rounded-xl ${{isFacebook ? 'bg-gradient-to-tr from-blue-700 to-indigo-600' : 'bg-gradient-to-tr from-indigo-700 to-purple-600'}} flex items-center justify-center font-bold text-white text-sm shadow-md">
                                    ${{acc.name.charAt(0).toUpperCase()}}
                                </div>
                                <div>
                                    <h3 class="text-sm font-bold text-white flex items-center gap-1.5">
                                        <span>${{escapeHtml(acc.name)}}</span>
                                    </h3>
                                    <div class="flex flex-wrap items-center gap-1.5 mt-1">
                                        <span class="text-[10px] text-gray-400 font-mono">${{acc.id}}</span>
                                        <span class="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-indigo-300 font-medium">${{acc.target_region}}</span>
                                        ${{platformBadge}}
                                        ${{sourcesBadge}}
                                    </div>
                                </div>
                            </div>
                            <div class="flex items-center gap-2">
                                <button onclick="toggleAccount('${{acc.id}}')" class="text-xs px-2.5 py-1 rounded-lg font-medium transition ${{acc.enabled ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-gray-800 text-gray-400'}}">
                                    ${{acc.enabled ? '啟用中' : '已暫停'}}
                                </button>
                            </div>
                        </div>

                        <!-- 戰役重大事件 Banner -->
                        ${{campaignBanner}}

                        <!-- 獨立 Agent 成長策略使命與排程 -->
                        <div class="text-[11px] bg-indigo-950/30 border border-indigo-900/40 p-2.5 rounded-xl space-y-1.5">
                            <div class="flex items-center justify-between text-indigo-400 font-bold text-[10px]">
                                <span>🎯 獨立 AI Agent 成長使命：</span>
                                <div class="flex flex-wrap items-center gap-1.5">${{scheduleBadge}} ${{fastTrackBadge}}</div>
                            </div>
                            <p class="text-indigo-200 line-clamp-2 leading-relaxed">
                                ${{escapeHtml(acc.strategy_prompt || '目標是吸取最多粉絲關注，優先挑選該領域最有料、最好笑之即時爆文。')}}
                            </p>
                        </div>

                        <!-- 參數詳細資訊 -->
                        <div class="grid grid-cols-2 gap-2.5 text-xs text-gray-300 bg-gray-950/60 p-3 rounded-xl border border-gray-800/60">
                            <div>
                                <span class="text-gray-500 block text-[11px]">特定遊戲名稱</span>
                                <span class="font-medium text-white truncate block mt-0.5">${{escapeHtml(acc.game_name)}}</span>
                            </div>
                            <div>
                                <span class="text-gray-500 block text-[11px]">監控來源關鍵字/板塊</span>
                                <span class="font-medium text-white block mt-0.5">${{escapeHtml(acc.subreddit || acc.game_name)}} (≥${{acc.min_upvotes}}讚)</span>
                            </div>
                            ${{acc.custom_tags ? `
                                <div class="col-span-2 text-[11px] text-indigo-300 font-mono flex items-center gap-1.5 pt-1 border-t border-gray-800/40">
                                    <span class="text-gray-400">🏷️ 標籤：</span>
                                    <span class="truncate font-semibold">${{escapeHtml(acc.custom_tags)}}</span>
                                </div>
                            ` : `
                                <div class="col-span-2 text-[11px] text-gray-400 font-mono flex items-center gap-1.5 pt-1 border-t border-gray-800/40">
                                    <span>🏷️ 標籤：</span>
                                    <span class="text-gray-400">🤖 AI 依遊戲自動生成最佳爆款標籤</span>
                                </div>
                            `}}
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
                                <button onclick="triggerAccount('${{acc.id}}', this)" ${{isRunning ? 'disabled' : ''}} class="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-3.5 py-1.5 rounded-lg text-xs font-bold transition shadow-sm flex items-center gap-1">
                                    <span>⚡ 點火此帳號</span>
                                </button>
                                <button onclick="copyAccountSession('${{acc.id}}', this)" class="bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 px-2.5 py-1.5 rounded-lg text-xs transition">
                                    <span>📋 複製 Session</span>
                                </button>
                                <button onclick="openMilestonesModal('${{acc.id}}')" class="bg-amber-950/60 hover:bg-amber-900 text-amber-300 border border-amber-800/60 px-2.5 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1">
                                    <span>📅 戰役大事記</span>
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

            function handleTargetPlatformChange(targetVal) {{
                const target = targetVal || document.getElementById('acc-target-platform').value;
                const labelSession = document.getElementById('label-session-cookie');
                const lblThreads = document.getElementById('lbl-source-threads');
                const chkThreads = document.getElementById('src-threads');

                if (target === 'Facebook') {{
                    labelSession.innerText = '🎯 該帳號專屬 Facebook【發布貼文】Cookie (JSON)*';
                    if (lblThreads) lblThreads.classList.remove('hidden');
                }} else {{
                    labelSession.innerText = '🎯 該帳號專屬 Threads【發布貼文】Cookie (JSON)*';
                    if (lblThreads) lblThreads.classList.add('hidden');
                    if (chkThreads) chkThreads.checked = false;
                }}
            }}

            function updateScheduleFields() {{
                const schedType = document.querySelector('input[name="schedule_type"]:checked')?.value || 'interval';
                const fixedBox = document.getElementById('sched-fixed-box');
                const intervalBox = document.getElementById('sched-interval-box');
                if (schedType === 'fixed_times') {{
                    fixedBox.classList.remove('hidden');
                    intervalBox.classList.add('hidden');
                }} else if (schedType === 'interval') {{
                    fixedBox.classList.add('hidden');
                    intervalBox.classList.remove('hidden');
                }} else {{
                    fixedBox.classList.add('hidden');
                    intervalBox.classList.add('hidden');
                }}
            }}

            function openAddAccountModal() {{
                document.getElementById('modal-account-title').innerText = '➕ 新增獨立 AI Agent 帳號工作台';
                document.getElementById('acc-id').value = '';
                document.getElementById('acc-name').value = '';
                document.getElementById('acc-game').value = '';
                document.getElementById('acc-subreddit').value = '';
                document.getElementById('acc-tags').value = '';
                document.getElementById('acc-strategy').value = '目標是最大化粉絲與關注度，優先挑選該領域最有料、最好笑之即時爆文。';
                document.getElementById('acc-upvotes').value = '100';
                document.getElementById('acc-session').value = '';
                document.getElementById('acc-enabled').checked = true;
                document.getElementById('acc-target-platform').value = 'Threads';
                document.getElementById('acc-discovery-mode').value = 'rising';

                document.getElementById('src-baha').checked = true;
                document.getElementById('src-reddit').checked = true;
                document.getElementById('src-x').checked = true;
                document.getElementById('src-twitch').checked = true;
                document.getElementById('src-threads').checked = false;

                document.getElementById('sched-interval').checked = true;
                document.getElementById('acc-interval-minutes').value = '180';
                document.getElementById('acc-fixed-times').value = '12:30, 18:30, 22:00';
                updateScheduleFields();

                document.getElementById('acc-enable-fast-track').checked = true;
                document.getElementById('acc-fast-track-min-upvotes').value = '300';
                document.getElementById('acc-cooldown-minutes').value = '45';

                handleTargetPlatformChange('Threads');
                populateRegionsSelect("台灣 (繁體中文)");
                document.getElementById('modal-account').classList.remove('hidden');
            }}

            function openEditAccountModal(accId) {{
                const acc = (currentData?.accounts || []).find(a => a.id === accId);
                if (!acc) return;

                document.getElementById('modal-account-title').innerText = '⚙️ 編輯獨立 AI Agent 帳號工作台';
                document.getElementById('acc-id').value = acc.id;
                document.getElementById('acc-name').value = acc.name || '';
                document.getElementById('acc-game').value = acc.game_name || '';
                document.getElementById('acc-subreddit').value = acc.subreddit || '';
                document.getElementById('acc-tags').value = acc.custom_tags || '';
                document.getElementById('acc-strategy').value = acc.strategy_prompt || '';
                document.getElementById('acc-upvotes').value = acc.min_upvotes || '100';
                document.getElementById('acc-enabled').checked = acc.enabled !== false;
                
                const targetPlat = acc.target_platform || 'Threads';
                document.getElementById('acc-target-platform').value = targetPlat;
                document.getElementById('acc-discovery-mode').value = acc.discovery_mode || 'rising';
                
                const sources = acc.source_platforms || [acc.source_platform || 'Reddit'];
                document.getElementById('src-baha').checked = sources.includes('巴哈姆特');
                document.getElementById('src-reddit').checked = sources.includes('Reddit');
                document.getElementById('src-x').checked = sources.includes('X');
                document.getElementById('src-twitch').checked = sources.includes('Twitch');
                document.getElementById('src-threads').checked = sources.includes('Threads');

                const schedType = acc.schedule_type || 'interval';
                if (schedType === 'fixed_times') document.getElementById('sched-fixed').checked = true;
                else if (schedType === 'manual') document.getElementById('sched-manual').checked = true;
                else document.getElementById('sched-interval').checked = true;

                document.getElementById('acc-fixed-times').value = acc.fixed_times || '12:30, 18:30, 22:00';
                document.getElementById('acc-interval-minutes').value = acc.interval_minutes || 180;
                updateScheduleFields();

                document.getElementById('acc-enable-fast-track').checked = acc.enable_fast_track !== false;
                document.getElementById('acc-fast-track-min-upvotes').value = acc.fast_track_min_upvotes || 300;
                document.getElementById('acc-cooldown-minutes').value = acc.cooldown_minutes || 45;

                handleTargetPlatformChange(targetPlat);
                populateRegionsSelect(acc.target_region || "台灣 (繁體中文)");

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

                const selectedSources = [];
                form.querySelectorAll('input[name="source_platforms"]:checked').forEach(cb => {{
                    selectedSources.push(cb.value);
                }});
                if (selectedSources.length === 0) {{
                    alert("請至少勾選一個來源監控雷達平台！");
                    return;
                }}

                const schedType = form.querySelector('input[name="schedule_type"]:checked')?.value || 'interval';

                const payload = {{
                    id: formData.get('id') || undefined,
                    name: formData.get('name'),
                    target_platform: formData.get('target_platform') || 'Threads',
                    source_platforms: selectedSources,
                    source_platform: selectedSources[0],
                    strategy_prompt: formData.get('strategy_prompt') || '',
                    schedule_type: schedType,
                    fixed_times: formData.get('fixed_times') || '12:30, 18:30, 22:00',
                    interval_minutes: parseInt(formData.get('interval_minutes') || '180', 10),
                    discovery_mode: formData.get('discovery_mode') || 'rising',
                    target_region: formData.get('target_region'),
                    game_name: formData.get('game_name'),
                    subreddit: formData.get('subreddit'),
                    custom_tags: formData.get('custom_tags') || '',
                    min_upvotes: parseInt(formData.get('min_upvotes') || '100', 10),
                    enable_fast_track: formData.get('enable_fast_track') === 'on',
                    fast_track_min_upvotes: parseInt(formData.get('fast_track_min_upvotes') || '300', 10),
                    cooldown_minutes: parseInt(formData.get('cooldown_minutes') || '45', 10),
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
                if (confirm("確定要刪除帳號工作台【" + name + "】嗎？\\n此操作將刪除此帳號的專屬設定與 Session。")) {{
                    await fetch(`/api/accounts/${{accId}}/delete`, {{ method: 'POST' }});
                    fetchDashboardData();
                }}
            }}

            async function triggerAccount(accId, btn) {{
                if (btn) {{
                    btn.disabled = true;
                    btn.innerText = '⏳ 啟動中...';
                }}
                await fetch(`/api/accounts/${{accId}}/trigger`, {{ method: 'POST' }});
                setTimeout(fetchDashboardData, 1000);
            }}

            async function triggerAllAccounts() {{
                const btn = document.getElementById('btn-trigger-all');
                if (btn) {{
                    btn.disabled = true;
                    btn.innerText = '⏳ 排隊點火中...';
                }}
                if (confirm("確定要一鍵點火所有已啟用的帳號工作台嗎？\\n系統將排隊依序執行每個帳號的搬運與發布任務。")) {{
                    await fetch('/api/trigger-all', {{ method: 'POST' }});
                    setTimeout(fetchDashboardData, 1000);
                }} else if (btn) {{
                    btn.disabled = false;
                    btn.innerHTML = '<span>⚡ 一鍵點火所有啟用帳號</span>';
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

            // 來源爬蟲 Cookie 管理 (X / FB 爬文)
            async function pasteToElement(elemId) {{
                try {{
                    const text = await navigator.clipboard.readText();
                    if (text) {{
                        document.getElementById(elemId).value = text;
                    }} else {{
                        alert("剪貼簿目前為空！");
                    }}
                }} catch (e) {{
                    alert("請手動在文字框內按 Ctrl+V 貼上 Cookie。");
                }}
            }}

            async function openGlobalCookiesModal() {{
                try {{
                    const res = await fetch('/api/global-cookies');
                    const d = await res.json();
                    
                    const xBadge = document.getElementById('badge-x-cookie-status');
                    const xArea = document.getElementById('global-x-cookie');
                    if (d.x && d.x.has_session) {{
                        xBadge.className = 'text-[10px] px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-700 font-semibold';
                        xBadge.innerText = `✅ 已配置 (${{d.x.cookies_count}} 筆 Cookie)`;
                        xArea.value = d.x.content || '';
                    }} else {{
                        xBadge.className = 'text-[10px] px-2 py-0.5 rounded-full bg-amber-950 text-amber-400 border border-amber-700 font-semibold';
                        xBadge.innerText = '⚠️ 尚未設定';
                        xArea.value = '';
                    }}

                    const fbBadge = document.getElementById('badge-fb-cookie-status');
                    const fbArea = document.getElementById('global-fb-scraper-cookie');
                    if (d.facebook_scraper && d.facebook_scraper.has_session) {{
                        fbBadge.className = 'text-[10px] px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-700 font-semibold';
                        fbBadge.innerText = `✅ 已配置 (${{d.facebook_scraper.cookies_count}} 筆 Cookie)`;
                        fbArea.value = d.facebook_scraper.content || '';
                    }} else {{
                        fbBadge.className = 'text-[10px] px-2 py-0.5 rounded-full bg-amber-950 text-amber-400 border border-amber-700 font-semibold';
                        fbBadge.innerText = '⚠️ 尚未設定';
                        fbArea.value = '';
                    }}

                    document.getElementById('modal-global-cookies').classList.remove('hidden');
                }} catch (e) {{
                    alert("載入爬蟲 Cookie 設定失敗: " + e);
                }}
            }}

            function closeGlobalCookiesModal() {{
                document.getElementById('modal-global-cookies').classList.add('hidden');
            }}

            async function saveGlobalCookie(platform) {{
                const elemId = platform === 'x' ? 'global-x-cookie' : 'global-fb-scraper-cookie';
                const val = document.getElementById(elemId).value.trim();
                if (!val) {{
                    if (!confirm("確定要清空此平台的爬蟲 Cookie 嗎？")) return;
                }}
                try {{
                    const res = await fetch('/api/global-cookies/save', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ platform: platform, cookie_data: val }})
                    }});
                    const d = await res.json();
                    if (d.status === 'success') {{
                        alert(d.message || "已儲存！");
                        openGlobalCookiesModal();
                    }} else {{
                        alert("儲存失敗: " + (d.message || "未知錯誤"));
                    }}
                }} catch (e) {{
                    alert("儲存請求失敗: " + e);
                }}
            }}

            // 矩陣營運情報簡報 Modal
            async function openAnalyticsModal() {{
                try {{
                    const res = await fetch('/api/analytics');
                    const d = await res.json();

                    document.getElementById('analytics-total-posts').innerText = d.total_posts || 0;
                    document.getElementById('analytics-fast-track-count').innerText = d.fast_track_count || 0;

                    // 來源分佈標籤
                    const srcBreakdown = document.getElementById('analytics-sources-breakdown');
                    const platforms = Object.entries(d.platform_breakdown || {{}});
                    if (platforms.length === 0) {{
                        srcBreakdown.innerHTML = '<span class="text-gray-500">無數據</span>';
                    }} else {{
                        srcBreakdown.innerHTML = platforms.map(([k, v]) => `
                            <span class="px-1.5 py-0.5 rounded bg-gray-800 text-sky-300 font-mono">${{escapeHtml(k)}}: ${{v}}</span>
                        `).join('');
                    }}

                    // 峰值時段
                    const hours = Object.entries(d.hour_breakdown || {{}});
                    if (hours.length > 0) {{
                        hours.sort((a, b) => b[1] - a[1]);
                        document.getElementById('analytics-peak-hour').innerText = `${{hours[0][0]}}:00 (共 ${{hours[0][1]}} 篇)`;
                    }} else {{
                        document.getElementById('analytics-peak-hour').innerText = '暫無';
                    }}

                    // 最近紀錄表格
                    const tbody = document.getElementById('analytics-table-body');
                    const logs = d.recent_logs || [];
                    if (logs.length === 0) {{
                        tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-gray-500">尚無營運數據記錄。系統定時巡航或手動點火成功後將自動記入！</td></tr>`;
                    }} else {{
                        tbody.innerHTML = logs.map(item => `
                            <tr class="hover:bg-gray-950/50">
                                <td class="p-2.5 font-mono text-gray-400 whitespace-nowrap">${{item.logged_at || ''}}</td>
                                <td class="p-2.5 font-medium text-white">${{escapeHtml(item.acc_name || item.acc_id)}}</td>
                                <td class="p-2.5"><span class="px-1.5 py-0.5 rounded bg-gray-800 text-sky-300 font-mono">${{escapeHtml(item.source_platform || '')}}</span></td>
                                <td class="p-2.5 max-w-[200px]">
                                    <div class="truncate font-medium text-gray-200" title="${{escapeHtml(item.title || '')}}">${{escapeHtml(item.title || item.post_id || '')}}</div>
                                    <div class="text-[10px] text-amber-400 font-mono">👍 ${{item.upvotes || 0}} 讚</div>
                                </td>
                                <td class="p-2.5 whitespace-nowrap">
                                    ${{item.is_fast_track 
                                        ? '<span class="px-2 py-0.5 rounded-full bg-amber-950 text-amber-300 border border-amber-800 font-bold text-[10px]">🚨 自主插隊</span>' 
                                        : '<span class="px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 text-[10px]">🕒 常規定時</span>'}}
                                </td>
                                <td class="p-2.5 text-gray-400 max-w-[240px] text-[11px] leading-relaxed">
                                    ${{escapeHtml(item.curation_reason || 'AI 綜合評選為最有料爆款')}}
                                </td>
                            </tr>
                        `).join('');
                    }}

                    document.getElementById('modal-analytics').classList.remove('hidden');
                }} catch (e) {{
                    alert("載入營運情報失敗: " + e);
                }}
            }}

            function closeAnalyticsModal() {{
                document.getElementById('modal-analytics').classList.add('hidden');
            }}

            // =================== 戰役重大事件日曆 Modal ===================
            let currentMilestonesAccId = null;

            async function openMilestonesModal(accId) {{
                currentMilestonesAccId = accId;
                const acc = (currentData?.accounts || []).find(a => a.id === accId);
                const accName = acc ? acc.name : accId;
                document.getElementById('milestones-modal-acc-title').innerText = `📅 【${{escapeHtml(accName)}}】戰役行事曆與重大事件`;
                document.getElementById('mile-acc-id').value = accId;

                try {{
                    const res = await fetch(`/api/accounts/${{accId}}/milestones`);
                    const d = await res.json();
                    renderMilestonesModalContent(d);
                    document.getElementById('modal-milestones').classList.remove('hidden');
                }} catch (e) {{
                    alert("載入戰役事件日曆失敗: " + e);
                }}
            }}

            function closeMilestonesModal() {{
                document.getElementById('modal-milestones').classList.add('hidden');
            }}

            function renderMilestonesModalContent(data) {{
                const camp = data.campaign_status || {{ phase: 'CRUISE', badge_text: '⚡ 常規巡航' }};
                const bannerEl = document.getElementById('milestones-active-banner');

                let bannerStyle = 'bg-indigo-950/40 border-indigo-800 text-indigo-300';
                let phaseDesc = '無緊急大作事件，維持常態爆文巡航掃描。';
                if (camp.phase === 'WARMUP') {{
                    bannerStyle = 'bg-amber-950/70 border-amber-500 text-amber-200 animate-pulse';
                    phaseDesc = '🔥 預熱衝刺期生效中！AI 自動加權優先挑選該大作之預告、規格、試玩與倒數爆文。';
                }} else if (camp.phase === 'LAUNCH_DAY') {{
                    bannerStyle = 'bg-red-950/80 border-red-500 text-red-200 font-bold';
                    phaseDesc = '🚨 正式引爆日！全網流量年度高峰，AI 優先鎖定首發實機體驗與初見神操作！';
                }} else if (camp.phase === 'AFTERMATH') {{
                    bannerStyle = 'bg-emerald-950/60 border-emerald-500 text-emerald-200';
                    phaseDesc = '📈 餘波收割期！AI 轉向鎖定逃課配裝、新手避坑、深度彩蛋與翻車笑點。';
                }}

                bannerEl.className = `p-3.5 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between text-xs gap-2 ${{bannerStyle}}`;
                bannerEl.innerHTML = `
                    <div>
                        <div class="font-bold text-sm">${{escapeHtml(camp.badge_text)}}</div>
                        <div class="text-[11px] opacity-90 mt-0.5">${{phaseDesc}}</div>
                    </div>
                    <span class="text-[10px] px-2 py-0.5 rounded bg-black/40 border border-white/20 whitespace-nowrap">階段：${{camp.phase}}</span>
                `;

                // 渲染現有事件
                const listEl = document.getElementById('milestones-list-container');
                const milestones = data.milestones || [];
                if (milestones.length === 0) {{
                    listEl.innerHTML = `<div class="text-xs text-gray-500 p-4 bg-gray-950/50 rounded-xl border border-gray-800 text-center">目前尚未排定任何未來重大事件。請在下方新增如《GTA 6》上市或新 DLC 測試！</div>`;
                }} else {{
                    listEl.innerHTML = milestones.map(m => `
                        <div class="bg-gray-950 border border-gray-800 p-3 rounded-xl flex items-center justify-between gap-3 text-xs">
                            <div class="space-y-1">
                                <div class="font-bold text-white flex items-center gap-2">
                                    <span>${{escapeHtml(m.title)}}</span>
                                    <span class="text-[10px] px-2 py-0.5 rounded bg-amber-950 text-amber-400 border border-amber-800 font-mono">📅 ${{m.target_date}}</span>
                                </div>
                                ${{m.notes ? `<p class="text-[11px] text-gray-400">${{escapeHtml(m.notes)}}</p>` : ''}}
                                ${{m.keywords && m.keywords.length > 0 ? `
                                    <div class="flex flex-wrap gap-1 pt-0.5">
                                        ${{m.keywords.map(k => `<span class="text-[9px] px-1.5 py-0.5 rounded bg-gray-900 text-gray-400">#${{escapeHtml(k)}}</span>`).join('')}}
                                    </div>
                                ` : ''}}
                            </div>
                            <button onclick="deleteMilestone('${{m.id}}')" class="text-gray-500 hover:text-red-400 px-2 py-1 text-xs transition">
                                🗑️ 刪除
                            </button>
                        </div>
                    `).join('');
                }}

                // 渲染 AI 探測候選
                const discEl = document.getElementById('milestones-discovered-container');
                const discovered = data.discovered || [];
                if (discovered.length === 0) {{
                    discEl.innerHTML = `<div class="text-xs text-gray-500 p-3 bg-gray-950/60 rounded-xl border border-gray-800 text-center">目前無待採納線索。AI 每次掃描貼文若探測到發售日或測試情報將自動在此推薦！</div>`;
                }} else {{
                    discEl.innerHTML = discovered.map(d => `
                        <div class="bg-purple-950/30 border border-purple-900/50 p-3 rounded-xl flex items-center justify-between gap-3 text-xs">
                            <div class="space-y-0.5">
                                <div class="font-bold text-purple-200 flex items-center gap-2">
                                    <span>💡 ${{escapeHtml(d.title)}}</span>
                                    <span class="text-[10px] text-purple-400 font-mono">預計：${{d.target_date}}</span>
                                </div>
                                <div class="text-[10px] text-gray-400 truncate max-w-md">來源線索：${{escapeHtml(d.source_title || '')}}</div>
                            </div>
                            <button onclick="approveDiscoveredMilestone('${{d.id}}')" class="bg-purple-600 hover:bg-purple-500 text-white font-bold px-3 py-1.5 rounded-lg text-xs whitespace-nowrap shadow-sm transition">
                                ✅ 採納加入戰役
                            </button>
                        </div>
                    `).join('');
                }}
            }}

            async function handleNewMilestoneSubmit(e) {{
                e.preventDefault();
                const accId = document.getElementById('mile-acc-id').value;
                const kwStr = document.getElementById('mile-keywords').value;
                const kwList = kwStr.split(/[,，]/).map(k => k.trim()).filter(k => k);

                const payload = {{
                    title: document.getElementById('mile-title').value.trim(),
                    target_date: document.getElementById('mile-target-date').value,
                    keywords: kwList,
                    notes: document.getElementById('mile-notes').value.trim(),
                    auto_discovered: false
                }};

                try {{
                    const res = await fetch(`/api/accounts/${{accId}}/milestones/save`, {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(payload)
                    }});
                    const d = await res.json();
                    if (d.status === 'success') {{
                        document.getElementById('mile-title').value = '';
                        document.getElementById('mile-keywords').value = '';
                        document.getElementById('mile-notes').value = '';
                        openMilestonesModal(accId);
                        fetchDashboardData();
                    }}
                }} catch (err) {{
                    alert("新增事件失敗: " + err);
                }}
            }}

            async function deleteMilestone(mId) {{
                if (!confirm("確定要刪除此重大事件嗎？")) return;
                const accId = currentMilestonesAccId;
                try {{
                    await fetch(`/api/accounts/${{accId}}/milestones/delete`, {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ id: mId }})
                    }});
                    openMilestonesModal(accId);
                    fetchDashboardData();
                }} catch (err) {{
                    alert("刪除事件失敗: " + err);
                }}
            }}

            async function approveDiscoveredMilestone(discId) {{
                const accId = currentMilestonesAccId;
                try {{
                    await fetch(`/api/accounts/${{accId}}/milestones/approve-discovered`, {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ id: discId }})
                    }});
                    openMilestonesModal(accId);
                    fetchDashboardData();
                }} catch (err) {{
                    alert("採納事件失敗: " + err);
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
