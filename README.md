# 🚀 跨平台遊戲熱文自動搬運系統 — 矩陣多帳號工作台版 (Reddit ➔ Threads)

低成本、24 小時運轉、**矩陣多帳號獨立工作台**、**100% 原文排版與語氣鏡像對齊**、**目標地區官方遊戲專有名詞精準對齊**、支援圖文與影片自動壓制上傳、免公開圖床、具備外接視覺化主控台與 Bug 一鍵複製診斷。

---

## 🌟 核心特色

1. **🏢 矩陣多社群帳號工作台（每組 Cookie 獨立運作）**
   - **每輸入一組社群 Cookie，就自動生成一個專屬的帳號工作台**。
   - 每個工作台彼此完全隔離，各自擁有專屬的：
     - 目標地區與語言（例如：帳號 A 發「台灣繁體中文」、帳號 B 發「越南語」、帳號 C 發「日本語」）。
     - 特定遊戲名稱（AI 自動抓取該遊戲在該地區官方伺服器的正版專有名詞與黑話）。
     - 來源 Subreddit 與最低讚數門檻。
     - 獨立去重歷史紀錄（互不干擾、避免跨帳號發布衝突）。
     - 獨立的即時發布進度條與錯誤診斷區。
2. **100% 格式與語氣鏡像翻譯（零增刪改動）**
   - 保持 1:1 的結構對齊，包括原文所有的段落換行、Emoji 表情符號、標點符號、大小寫語氣。
   - 嚴格保留原作者的所有情緒、語感與語調（憤怒、吐槽、激動、諷刺或冷靜）。
   - 絕不擅自添加「筆者認為」、「大家好」、「這是一篇翻譯」等客套廢話。
3. **AI 中轉站無縫接軌**
   - 支援所有 OpenAI 相容協議中轉站（OneAPI / NewAPI / RelayRouter 等）。
   - 所有帳號共用一個 AI 大腦，亦支援模型自動降級備援（如 `gemini-2.5-flash` ➔ `gemini-3.8-flash` ➔ `gpt-4o-mini`）。
4. **Playwright 網頁自動化發布（免圖床、免官方 API 審核）**
   - 本地檔案直接拖曳/上傳至 Threads，**完全不需要另外花錢租圖床或 CDN 伺服器**。
   - 採用 Session Cookie 登入機制，繞過機房 IP 與雙步驟驗證干擾。
5. **💬 24H Threads 留言區海巡獲客 Agent（精準獲客公關）**
   - **全自動雷達海巡**：24 小時定時在 Threads 官方搜尋指定遊戲/主題關鍵字（如：魔物獵人、MHWilds、荒野、傳說對決），即時嗅探討論熱度高的新貼文。
   - **真人玩家同行者神回覆（AI Witty Commenter）**：以「同為熱愛該遊戲、有生活感、幽默自嘲」的真實玩家視角切入，產出精煉（1~2 句）且充滿社群黑話的神回覆，絕無「求追蹤/小編」等廣告感。
   - **高轉換導流閉環**：當路人被神回覆吸引點進個人主頁時，看到的是充滿動態倒數生活感的 Bio 與滿滿熱門精華，自然大幅提升追蹤轉換率。
   - **嚴格防封控機制**：支援每日安全上限（預設 10 則）、單次巡邏上限（預設 1~2 則）、自動過濾自身帳號與歷史重複留言。
6. **🧬 動態真人 Bio 隨重大戰役動態更新與自動同步**
   - 擺脫搬運工的冰冷機器感，隨遊戲發售日、測試倒數或新賽季節奏自動推演具生活感的自我介紹。
   - 支援每日定時自動透過 Playwright 無縫同步至 Threads 個人主頁。
7. **外接視覺化主控台（Web Dashboard）**
   - **單一/批次點火**：支援「⚡ 點火此帳號」獨立發布，也支援「⚡ 一鍵點火所有啟用帳號」全域批次發布。
   - **海巡獲客面板**：提供「💬 海巡獲客」專屬彈窗，支援即時查看今日留言進度、自訂監控關鍵字、一鍵觸發手動海巡、以及審閱歷史神回覆記錄。
   - **獨立 Bug 診斷**：若任一帳號執行遇到例外，該卡片直接展開紅色錯誤區，清楚標註出錯步驟並提供「📋 複製錯誤日誌」按鈕。
8. **零伺服器成本運轉（GitHub Actions + 外接點火器）**
   - 支援透過 cron-job.org 發送 Webhook 喚醒 GitHub Actions 免費運行，依序為所有啟用的帳號排隊發布。

---

## 📁 專案檔案結構

```text
auto_threads_poster/
├── .github/
│   └── workflows/
│       └── auto_poster.yml      # GitHub Actions 自動發布工作流 (支援外部點火)
├── accounts/                    # 矩陣多帳號獨立工作台目錄
│   ├── accounts.json            # 帳號工作台清單 (已設 .gitignore 防洩漏)
│   ├── accounts.example.json    # 帳號設定範本
│   └── <account_id>/           # 每個帳號的獨立資料夾
│       ├── session.json         # 該帳號專屬的 Cookie Session (已排除)
│       └── history.json         # 該帳號已發布貼文去重紀錄
├── account_manager.py           # 矩陣帳號管理核心模組 (載入、儲存、遷移)
├── ai_engine.py                 # AI 中轉站大腦 (100% 格式鏡像 + 地區專有名詞轉換)
├── reddit_scraper.py            # Playwright 無痕模式 Reddit 熱門貼文採集器 (防 403 阻擋)
├── media_handler.py             # 圖片下載與 yt-dlp 影音合成壓制器
├── threads_playwright.py        # Playwright Threads 自動登入與直傳發文引擎
├── threads_commenter.py         # Threads 24H 留言區海巡獲客與神回覆引擎
├── main.py                      # 主調度流程 (支援 --account <id>, --all 與 --patrol)
├── dashboard.py                 # 矩陣多帳號視覺化主控台 (FastAPI + Tailwind)
├── login_local.py               # 本機一次性登入導出 Session 工具
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

### 第二步：啟動多帳號主控台
```powershell
python dashboard.py
```
在瀏覽器打開：👉 **http://127.0.0.1:8000**

1. **設定 AI 中轉大腦**：
   - 點擊右上角 **「🧠 AI 中轉大腦設定」**。
   - 填入您的 Base URL（如 `https://api.relayrouter.ai/v1`）、API Key 與模型名稱（如 `gemini-2.5-flash`）。
2. **新增社群帳號工作台**：
   - 點擊右上角 **「➕ 新增社群帳號工作台」**。
   - 輸入帳號名稱（例如：`@my_threads_tw (魔物獵人)`）。
   - 選擇受眾地區與語言（例如：`台灣 (繁體中文)` 或 `越南 (Tiếng Việt)`）。
   - 輸入特定遊戲名稱（例如：`Monster Hunter Wilds`）。
   - 輸入監控 Subreddit（例如：`MonsterHunter`）與熱門讚數門檻。
   - 貼入該帳號的 Threads Cookie Session (JSON)。
   - 點擊儲存，工作台立即生成！
3. **點火發布**：
   - 可在該工作台卡片點擊 **「⚡ 點火此帳號」** 進行單一測試。
   - 或點擊右上角 **「⚡ 一鍵點火所有啟用帳號」** 進行全域批次自動發文！

---

## 🍪 如何獲取各帳號的 Session Cookie？

若您需要新增第 2 個、第 3 個 Threads 帳號的 Cookie：
1. 在終端機執行：
   ```powershell
   python login_local.py
   ```
2. 彈出瀏覽器後，登入您的另一個 Threads 帳號。
3. 登入成功後回到終端機按 Enter，目錄下會更新 `threads_session.json`。
4. 打開主控台點擊「➕ 新增社群帳號工作台」，把該檔案內容貼入 Session 輸入框即可！

---

## 🖥️ 終端機 CLI 使用指令

主調度器 `main.py` 支援以下命令列參數：

```powershell
# 執行所有已啟用的帳號工作台（預設批次模式）
python main.py --all

# 指定單一帳號工作台執行
python main.py --account acc_primary

# 執行指定帳號的 Threads 留言區海巡獲客
python main.py --account acc_primary --patrol
```

---

## ☁️ 雲端 0 元定時運作教學 (GitHub Actions + 點火器)

專案已預設相容 GitHub Actions 矩陣排程：

1. **推送代碼至 GitHub**：
   ```powershell
   git add .
   git commit -m "feat: multi-account workspaces"
   git push origin main
   ```
   *(注意：`.gitignore` 已嚴格排除所有帳號的 `session.json` 與 API Key，100% 安全)*

2. **設定 GitHub Secrets**：
   在倉庫設定 `AI_BASE_URL` 與 `AI_API_KEY`。

3. **外接點火器 (cron-job.org)**：
   每次發送 Webhook 喚醒 GitHub Actions 時，系統會自動執行 `python main.py --all`，依序走訪所有啟用的帳號工作台並完成搬運發布！
