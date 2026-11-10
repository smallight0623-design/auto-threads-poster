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

app = FastAPI(title="Threads 熱文自動發布主控台")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
SESSION_FILE = os.path.join(BASE_DIR, "threads_session.json")
ERROR_LOG_FILE = os.path.join(BASE_DIR, "logs", "latest_error.json")
STATUS_FILE = os.path.join(BASE_DIR, "logs", "current_status.json")

DEFAULT_CONFIG = {
    "SOURCE_PLATFORM": "Reddit",
    "TARGET_PLATFORM": "Threads",
    "SUBREDDIT": "MonsterHunter",
    "MIN_UPVOTES": "100",
    "GAME_NAME": "Monster Hunter Wilds",
    "TARGET_REGION": "台灣 (繁體中文)",
    "AI_BASE_URL": "https://api.relayrouter.ai/v1",
    "AI_API_KEY": "",
    "AI_MODEL": "gemini-2.5-flash",
    "TRIGGER_INFO": "支援 cron-job.org 外部點火 (repository_dispatch) 或定時執行"
}

def get_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_CONFIG

def get_existing_session():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""

def get_error_log():
    if os.path.exists(ERROR_LOG_FILE):
        try:
            with open(ERROR_LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"status": "SUCCESS", "message": "目前無任何錯誤紀錄，系統運作正常。"}

def get_live_status():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"state": "IDLE", "step": "等待觸發", "message": "尚未發起執行任務"}

@app.get("/api/status")
async def api_status():
    status = get_live_status()
    error = get_error_log()
    return JSONResponse({"status": status, "error": error})

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    cfg = get_config()
    err = get_error_log()
    existing_session = get_existing_session()
    session_exists = bool(existing_session)
    is_failed = err.get("status") == "FAILED"

    regions = ["台灣 (繁體中文)", "越南 (Tiếng Việt)", "日本 (日本語)", "韓國 (한국어)", "香港 (繁體中文)", "北美 (English)"]
    region_options_html = ""
    for r in regions:
        selected = "selected" if cfg.get("TARGET_REGION") == r else ""
        region_options_html += f'<option value="{r}" {selected}>{r}</option>'

    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-TW" class="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Threads 熱文自動搬運主控台</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            tailwind.config = {{ darkMode: 'class' }}
            function copyError() {{
                const text = document.getElementById('error-trace').innerText;
                navigator.clipboard.writeText(text).then(() => {{
                    const btn = document.getElementById('copy-btn');
                    btn.innerText = '✅ 已複製錯誤日誌！';
                    setTimeout(() => {{ btn.innerText = '📋 一鍵複製完整錯誤日誌'; }}, 2500);
                }});
            }}
            function copySession() {{
                const area = document.getElementById('session-textarea');
                navigator.clipboard.writeText(area.value).then(() => {{
                    const btn = document.getElementById('copy-session-btn');
                    btn.innerText = '✅ 已複製 Session！';
                    setTimeout(() => {{ btn.innerText = '📋 複製 Session'; }}, 2000);
                }});
            }}
        </script>
    </head>
    <body class="bg-gray-950 text-gray-100 min-h-screen p-4 md:p-8 font-sans">
        <div class="max-w-4xl mx-auto space-y-6">
            <!-- 頁首 Header -->
            <div class="flex flex-col md:flex-row md:items-center justify-between border-b border-gray-800 pb-5 gap-4">
                <div>
                    <h1 class="text-2xl font-bold text-white flex items-center gap-2">
                        🚀 熱文自動搬運系統 — 智慧主控台
                    </h1>
                    <p class="text-xs text-gray-400 mt-1">
                        100% 格式語氣照抄鏡像翻譯 ‧ 目標地區遊戲專有名詞精準對齊 ‧ 外部點火免伺服器成本
                    </p>
                </div>
                <div class="flex items-center gap-2">
                    <button id="trigger-btn" onclick="triggerNow()" class="bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl text-sm font-bold transition shadow-lg shadow-indigo-600/30 flex items-center gap-2">
                        <span id="trigger-icon">⚡</span>
                        <span id="trigger-text">立即手動點火發布</span>
                    </button>
                </div>
            </div>

            <!-- 即時動態進度提示條 (點火後自動展開) -->
            <div id="live-progress-box" class="hidden bg-gray-900 border border-indigo-500/50 p-4 rounded-2xl shadow-xl transition-all">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-3">
                        <div id="status-spinner" class="animate-spin rounded-full h-5 w-5 border-2 border-indigo-400 border-t-transparent"></div>
                        <div>
                            <span id="status-step-badge" class="text-xs font-semibold px-2 py-0.5 rounded bg-indigo-900/80 text-indigo-300">執行中</span>
                            <span id="status-message" class="text-sm font-medium text-gray-200 ml-2">正在處理中...</span>
                        </div>
                    </div>
                    <span id="status-time" class="text-xs text-gray-400"></span>
                </div>
            </div>

            <!-- 表單設定 -->
            <form action="/save" method="POST" class="space-y-6">
                <!-- 1. 地區與遊戲專有詞庫設定 (受眾定義) -->
                <div class="bg-gray-900 p-6 rounded-2xl border border-gray-800 space-y-4 shadow-sm">
                    <div class="flex items-center gap-2 text-indigo-400 font-semibold text-base">
                        <span>🎯 1. 目標地區與遊戲專有詞庫設定（受眾範圍）</span>
                    </div>
                    <p class="text-xs text-gray-400">
                        系統將嚴格【100% 照抄原貼文之排版、換行、表情符號與語氣】，僅依您指定的「地區」自動對齊該語言並轉換為該地區官方遊戲專有名詞。
                    </p>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                        <div>
                            <label class="block text-xs font-medium text-gray-300 mb-1">目標地區與語言 (Target Region & Language)</label>
                            <select name="TARGET_REGION" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm focus:border-indigo-500 focus:outline-none">
                                {region_options_html}
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-300 mb-1">特定遊戲名稱 (供 AI 提取該地區官方術語與黑話)</label>
                            <input name="GAME_NAME" value="{cfg['GAME_NAME']}" placeholder="例如：Monster Hunter Wilds / 原神" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm focus:border-indigo-500 focus:outline-none">
                        </div>
                    </div>
                </div>

                <!-- 2. 監控來源與門檻 -->
                <div class="bg-gray-900 p-6 rounded-2xl border border-gray-800 space-y-4 shadow-sm">
                    <div class="flex items-center gap-2 text-blue-400 font-semibold text-base">
                        <span>📡 2. 來源監控與篩選門檻</span>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                            <label class="block text-xs font-medium text-gray-300 mb-1">來源平台</label>
                            <input name="SOURCE_PLATFORM" value="{cfg['SOURCE_PLATFORM']}" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm" readonly>
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-300 mb-1">監控 Subreddit 板塊名稱</label>
                            <input name="SUBREDDIT" value="{cfg['SUBREDDIT']}" placeholder="例如：MonsterHunter" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm focus:border-blue-500 focus:outline-none">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-300 mb-1">最低熱門讚數 (Min Upvotes)</label>
                            <input type="number" name="MIN_UPVOTES" value="{cfg['MIN_UPVOTES']}" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm focus:border-blue-500 focus:outline-none">
                        </div>
                    </div>
                </div>

                <!-- 3. AI 中轉站大腦設定 -->
                <div class="bg-gray-900 p-6 rounded-2xl border border-gray-800 space-y-4 shadow-sm">
                    <div class="flex items-center gap-2 text-purple-400 font-semibold text-base">
                        <span>🧠 3. AI 大腦中轉站設定 (相容所有 OpenAI / OneAPI 協議)</span>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div class="md:col-span-3">
                            <label class="block text-xs font-medium text-gray-300 mb-1">中轉站 Base URL (Endpoint)</label>
                            <input name="AI_BASE_URL" value="{cfg['AI_BASE_URL']}" placeholder="https://api.your-relay.com/v1" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm font-mono focus:border-purple-500 focus:outline-none">
                        </div>
                        <div class="md:col-span-2">
                            <label class="block text-xs font-medium text-gray-300 mb-1">中轉站 API Key (密鑰)</label>
                            <input type="password" name="AI_API_KEY" value="{cfg['AI_API_KEY']}" placeholder="sk-..." class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm font-mono focus:border-purple-500 focus:outline-none">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-300 mb-1">模型代號 (Model)</label>
                            <input name="AI_MODEL" value="{cfg['AI_MODEL']}" placeholder="gemini-2.5-flash" class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-sm font-mono focus:border-purple-500 focus:outline-none">
                        </div>
                    </div>
                </div>

                <!-- 4. Threads Cookie Session 注入 -->
                <div class="bg-gray-900 p-6 rounded-2xl border border-gray-800 space-y-4 shadow-sm">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-2 text-amber-400 font-semibold text-base">
                            <span>🍪 4. Threads Cookie Session 管理</span>
                        </div>
                        <div class="flex items-center gap-2">
                            <span class="text-xs px-2.5 py-1 rounded-full font-medium {'bg-emerald-950 text-emerald-400 border border-emerald-800' if session_exists else 'bg-red-950 text-red-400 border border-red-800'}">
                                {'✅ Session 已儲存並運作中' if session_exists else '⚠️ 尚未匯入 Session'}
                            </span>
                            {f'<button type="button" id="copy-session-btn" onclick="copySession()" class="bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 px-2.5 py-1 rounded text-xs transition">📋 複製 Session</button>' if session_exists else ''}
                        </div>
                    </div>
                    <p class="text-xs text-gray-400">
                        下方為目前保存在伺服器上的 Cookie Session 資料。您可在此檢視、備份或替換新的 Session：
                    </p>
                    <textarea id="session-textarea" name="COOKIE_SESSION_DATA" rows="4" placeholder='{{"cookies": [...], "origins": [...]}}' class="w-full bg-gray-950 border border-gray-700 rounded-lg p-2.5 text-xs font-mono focus:border-amber-500 focus:outline-none">{existing_session}</textarea>
                </div>

                <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-500 text-white py-3.5 rounded-xl font-bold transition shadow-lg shadow-emerald-900/30">
                    💾 儲存所有更新設定
                </button>
            </form>

            <!-- 5. Bug 回報與診斷專區 -->
            <div id="error-section" class="bg-gray-900 p-6 rounded-2xl border {'border-red-600/60 shadow-lg shadow-red-950/40' if is_failed else 'border-gray-800'} space-y-4">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                        <h2 class="text-base font-bold {'text-red-400' if is_failed else 'text-emerald-400'} flex items-center gap-2">
                            <span>{'🚨 系統錯誤診斷區 (Bug Report)' if is_failed else '🟢 系統健康度 (System Status)'}</span>
                        </h2>
                        <p class="text-xs text-gray-400 mt-1">若執行發生例外，此處將保留完整出錯步驟與 Python Traceback</p>
                    </div>
                    <button id="copy-btn" onclick="copyError()" class="bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 px-3.5 py-2 rounded-lg text-xs font-medium transition self-start sm:self-auto">
                        📋 一鍵複製完整錯誤日誌
                    </button>
                </div>

                <div class="bg-black/70 p-4 rounded-xl border border-gray-800 text-xs font-mono space-y-2">
                    <div class="flex flex-wrap gap-4 text-gray-400 pb-2 border-b border-gray-800">
                        <span>狀態：<strong id="err-status" class="{'text-red-400' if is_failed else 'text-emerald-400'}">{err.get('status')}</strong></span>
                        <span>最後記錄時間：<span id="err-time" class="text-gray-200">{err.get('timestamp', '無')}</span></span>
                        <span id="err-step-wrap">{f"<span>出錯階段：<span id='err-step' class='text-amber-400 font-semibold'>{err.get('failed_step')}</span></span>" if err.get('failed_step') else ""}</span>
                    </div>
                    <pre id="error-trace" class="text-gray-300 whitespace-pre-wrap max-h-72 overflow-y-auto leading-relaxed">{err.get('traceback', err.get('message', '目前一切正常，無錯誤。'))}</pre>
                </div>
            </div>
        </div>

        <script>
            let pollingTimer = null;

            async function checkStatus() {{
                try {{
                    const res = await fetch('/api/status');
                    const data = await res.json();
                    const live = data.status;
                    const err = data.error;

                    const liveBox = document.getElementById('live-progress-box');
                    const badge = document.getElementById('status-step-badge');
                    const msg = document.getElementById('status-message');
                    const timeEl = document.getElementById('status-time');
                    const spinner = document.getElementById('status-spinner');
                    const btn = document.getElementById('trigger-btn');
                    const icon = document.getElementById('trigger-icon');
                    const btnText = document.getElementById('trigger-text');

                    liveBox.classList.remove('hidden');
                    badge.innerText = live.step || '處理中';
                    msg.innerText = live.message || '';
                    timeEl.innerText = live.timestamp || '';

                    if (live.state === 'RUNNING') {{
                        spinner.classList.remove('hidden');
                        badge.className = 'text-xs font-semibold px-2 py-0.5 rounded bg-indigo-900/80 text-indigo-300';
                        btn.disabled = true;
                        btn.classList.add('opacity-75');
                        icon.innerText = '⏳';
                        btnText.innerText = '正在執行發布流程...';
                    }} else if (live.state === 'SUCCESS') {{
                        spinner.classList.add('hidden');
                        badge.className = 'text-xs font-semibold px-2 py-0.5 rounded bg-emerald-900/80 text-emerald-300';
                        btn.disabled = false;
                        btn.classList.remove('opacity-75');
                        icon.innerText = '⚡';
                        btnText.innerText = '立即手動點火發布';
                        clearInterval(pollingTimer);
                    }} else if (live.state === 'FAILED') {{
                        spinner.classList.add('hidden');
                        badge.className = 'text-xs font-semibold px-2 py-0.5 rounded bg-red-900/80 text-red-300';
                        btn.disabled = false;
                        btn.classList.remove('opacity-75');
                        icon.innerText = '⚡';
                        btnText.innerText = '立即手動點火發布';
                        
                        // 更新下方錯誤區塊並平滑滾動至錯誤區
                        if (err && err.traceback) {{
                            document.getElementById('err-status').innerText = 'FAILED';
                            document.getElementById('err-status').className = 'text-red-400';
                            document.getElementById('err-time').innerText = err.timestamp || '';
                            document.getElementById('err-step-wrap').innerHTML = `出錯階段：<span class='text-amber-400 font-semibold'>${{err.failed_step || ''}}</span>`;
                            document.getElementById('error-trace').innerText = err.traceback;
                            document.getElementById('error-section').scrollIntoView({{ behavior: 'smooth' }});
                        }}
                        clearInterval(pollingTimer);
                    }}
                }} catch (e) {{
                    console.error("狀態輪詢出錯:", e);
                }}
            }}

            async function triggerNow() {{
                const btn = document.getElementById('trigger-btn');
                btn.disabled = true;
                
                const liveBox = document.getElementById('live-progress-box');
                liveBox.classList.remove('hidden');
                document.getElementById('status-step-badge').innerText = '啟動中';
                document.getElementById('status-message').innerText = '正在發起執行請求...';

                await fetch('/trigger', {{ method: 'POST' }});
                
                // 每 1.5 秒自動輪詢一次即時狀態
                if (pollingTimer) clearInterval(pollingTimer);
                pollingTimer = setInterval(checkStatus, 1500);
            }}
        </script>
    </body>
    </html>
    """
    return html_content

@app.post("/save")
async def save_settings(request: Request):
    form = await request.form()
    data = dict(form)

    session_data = data.pop("COOKIE_SESSION_DATA", "").strip()
    if session_data:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            f.write(session_data)

    current_config = get_config()
    current_config.update(data)

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(current_config, f, indent=2, ensure_ascii=False)

    return HTMLResponse("<script>alert('設定已成功儲存！'); window.location.href='/';</script>")

@app.post("/trigger")
async def trigger_run():
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "main.py")], cwd=BASE_DIR, env=env)
    return {"status": "triggered"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
