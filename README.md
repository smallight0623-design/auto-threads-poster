# 🚀 跨平台遊戲熱文自動搬運發布系統 (Reddit ➔ Threads)

低成本、24 小時運轉、**100% 原文排版與語氣鏡像對齊**、**目標地區官方遊戲專有名詞精準對齊**、支援圖文與影片自動壓制上傳、免公開圖床、具備外接視覺化主控台與 Bug 一鍵複製診斷。

---

## 🌟 核心特色

1. **100% 格式與語氣鏡像翻譯（零增刪改動）**
   - 保持 1:1 的結構對齊，包括原文所有的段落換行、Emoji 表情符號、標點符號、大小寫語氣。
   - 嚴格保留原作者的所有情緒、語感與語調（憤怒、吐槽、激動、諷刺或冷靜）。
   - 絕不擅自添加「筆者認為」、「大家好」、「這是一篇翻譯」等客套廢話。
2. **受眾僅限地區與語言切換（專有名詞極致對齊）**
   - 依您指定的「目標地區」（例如：`台灣 (繁體中文)`、`越南 (Tiếng Việt)`、`日本 (日本語)`），AI 自動切換該地區玩家母語。
   - 自動將該遊戲在當地的**官方伺服器正版名詞、角色、裝備、技能與玩家社群常見黑話**精準置換。
3. **AI 中轉站無縫接軌**
   - 支援所有 OpenAI 相容協議中轉站（OneAPI / NewAPI / RelayRouter 等）。
   - 支援自動備援降級（若主力模型如 `gemini-2.5-flash` 遇不可用，自動切換 `gemini-3.8-flash` 或 `gpt-4o-mini` 重試）。
4. **Playwright 網頁自動化發布（免圖床、免官方 API 審核）**
   - 本地檔案直接拖曳/上傳至 Threads，**完全不需要另外花錢租圖床或 CDN 伺服器**。
   - 採用 Session Cookie 登入機制，繞過機房 IP 與雙步驟驗證干擾。
5. **外接視覺化主控台（Web Dashboard）**
   - 線上視覺化設定監控板塊、讚數門檻、地區語言、AI 中轉站與 Cookie Session。
   - **即時執行狀態面板**：點火後頂部動態顯示旋轉動畫與即時進度（`[抓取貼文]` ➔ `[AI 翻譯]` ➔ `[媒體處理]` ➔ `[Threads 發布]`）。
   - **Bug 診斷與一鍵複製**：若執行遇到任何例外，頁面自動滾動至錯誤區，清楚標註出錯步驟並提供「📋 一鍵複製完整錯誤日誌」按鈕。
6. **零伺服器成本運轉（GitHub Actions + 外接點火器）**
   - 支援透過 cron-job.org 發送 Webhook 喚醒 GitHub Actions 免費運行，杜絕 GitHub 原生定時排程的延遲與休眠。

---

## 📁 專案檔案結構

```text
auto_threads_poster/
├── .github/
│   └── workflows/
│       └── auto_poster.yml      # GitHub Actions 自動發布工作流 (支援外部點火)
├── ai_engine.py                 # AI 中轉站大腦 (100% 格式鏡像 + 地區專有名詞轉換)
├── reddit_scraper.py            # Playwright 無痕模式 Reddit 熱門貼文採集器 (防 403 阻擋)
├── media_handler.py             # 圖片下載與 yt-dlp 影音合成壓制器
├── threads_playwright.py        # Playwright Threads 自動登入與直傳發文引擎
├── main.py                      # 主調度流程 (即時狀態回傳、去重與全域例外捕捉)
├── dashboard.py                 # 視覺化主控台 Web 服務 (FastAPI + Tailwind)
├── login_local.py               # 本機一次性登入導出 Session 工具
├── config.example.json          # 設定檔範本
├── posted_ids.json              # 歷史發布貼文 ID 去重紀錄
├── requirements.txt             # Python 依賴清單
└── README.md                    # 專案說明文件
```

---

## 🛠️ 本地安裝與快速使用教學

### 第一步：安裝環境依賴
在終端機切換至專案資料夾後執行：
```powershell
pip install -r requirements.txt
playwright install chromium
```

### 第二步：取得您的 Threads 登入 Session
在終端機執行一次性登入工具：
```powershell
python login_local.py
```
1. 系統會自動彈出 Chromium 視窗，前往 Threads 登入頁。
2. 請正常登入您的 Threads 帳號（若有兩步驟驗證請手動完成）。
3. 登入完成並看到首頁後，回到終端機按 `Enter` 鍵。
4. 專案目錄下會自動產生 `threads_session.json`。

### 第三步：啟動視覺化主控台
```powershell
python dashboard.py
```
在瀏覽器打開：👉 **http://127.0.0.1:8000**

1. **設定受眾地區**：選擇 `台灣 (繁體中文)` 或其他國家。
2. **輸入遊戲名稱**：例如 `Monster Hunter Wilds`。
3. **設定 AI 中轉站**：填入您的 Base URL（如 `https://api.relayrouter.ai/v1`）、API Key 與模型名稱。
4. **確認 Session**：主控台會自動載入剛剛生成的 Session，顯示 `✅ Session 已儲存並運作中`。
5. 點擊 **「💾 儲存所有更新設定」**。
6. 點擊右上角 **「⚡ 立即手動點火發布」**，即可在頂部看到即時動態發布進度！

---

## ☁️ 雲端 0 元定時運作教學 (GitHub Actions + 點火器)

若希望電腦關機時也能 24 小時定時自動發文，可部署至 GitHub 免費執行：

### 1. 推送至 GitHub
在 GitHub 上建立一個公開倉庫（如 `auto-threads-poster`），將代碼推送上去：
```powershell
git init
git add .
git commit -m "feat: initial commit"
git branch -M main
git remote add origin https://github.com/{你的用戶名}/auto-threads-poster.git
git push -u origin main
```
*(注意：`.gitignore` 已嚴密過濾您的 Session 與 API Key，不會外洩)*

### 2. 設定 GitHub Secrets
進入倉庫的 **Settings ➔ Secrets and variables ➔ Actions**，點擊 **New repository secret** 新增以下金鑰：
- `AI_BASE_URL`：您使用的中轉站網址（如 `https://api.relayrouter.ai/v1`）
- `AI_API_KEY`：您的 AI 密鑰（如 `sk-...`）
- `THREADS_SESSION_DATA`：開啟本機的 `threads_session.json`，將全部 JSON 內容複製貼入

### 3. 設定 cron-job.org 免費外接點火器
1. 前往 [cron-job.org](https://cron-job.org/) 免費註冊帳號。
2. 建立新任務（Create Cronjob）：
   - **URL**: `https://api.github.com/repos/{你的用戶名}/{你的倉庫}/dispatches`
   - **Method**: `POST`
   - **Headers**:
     - `Accept`: `application/vnd.github.v3+json`
     - `Authorization`: `Bearer 你的_GITHUB_PERSONAL_ACCESS_TOKEN` *(需具有 repo 與 workflow 權限)*
     - `User-Agent`: `Mozilla/5.0`
   - **Body (JSON)**:
     ```json
     {"event_type": "external_trigger"}
     ```
   - **執行時間**：設定於目標受眾活躍的尖峰時段（例如每天台灣時間 `12:00`、`18:30`、`21:30`）。
3. 時間一到，點火器會發送 Webhook，GitHub Actions 虛擬機秒速啟動，自動爬取、翻譯並發布至 Threads！

---

## 🚨 錯誤排查與診斷 (Bug Diagnostic)

如果發布未如預期成功：
1. 進入主控台（`http://127.0.0.1:8000`）最下方的 **「系統錯誤診斷區」**。
2. 系統會以紅字明確標示出錯階段（例如：`[來源平台爬取階段]`、`[AI 中轉站翻譯階段]` 或 `[Playwright 自動發布階段]`）。
3. 點擊 **「📋 一鍵複製完整錯誤日誌」** 按鈕，即可獲得完整的 Python 呼叫堆疊（Traceback），直接貼給技術人員即可秒速除錯。
