import os
import sys
import json
import traceback
import datetime
import asyncio

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from reddit_scraper import fetch_top_reddit_posts
from ai_engine import call_ai_proxy
from media_handler import download_media
from threads_playwright import post_to_threads

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json") if os.path.exists(os.path.join(BASE_DIR, "config.json")) else os.path.join(BASE_DIR, "config.example.json")
HISTORY_FILE = os.path.join(BASE_DIR, "posted_ids.json")
ERROR_LOG_FILE = os.path.join(BASE_DIR, "logs", "latest_error.json")
STATUS_FILE = os.path.join(BASE_DIR, "logs", "current_status.json")

def update_status(step: str, message: str, state: str = "RUNNING"):
    """更新即時執行狀態，供主控台動態輪詢顯示"""
    os.makedirs("logs", exist_ok=True)
    payload = {
        "state": state,
        "step": step,
        "message": message,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"[{state}] {step}: {message}")

def record_error(step: str, err: Exception):
    """將錯誤原因、步驟與呼叫堆疊完整記錄至日誌檔，供主控台讀取與一鍵複製"""
    os.makedirs("logs", exist_ok=True)
    error_payload = {
        "status": "FAILED",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "failed_step": step,
        "error_message": str(err),
        "traceback": traceback.format_exc()
    }
    with open(ERROR_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(error_payload, f, indent=2, ensure_ascii=False)
    
    update_status(step, f"執行失敗: {str(err)}", state="FAILED")
    print(f"\n❌ 錯誤已捕捉並記錄至主控台：[{step}] {str(err)}")

async def main():
    update_status("初始化", "讀取設定檔與去重紀錄...")
    if not os.path.exists(CONFIG_FILE):
        record_error("設定讀取", FileNotFoundError(f"找不到 {CONFIG_FILE} 設定檔"))
        return

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    subreddit = config.get("SUBREDDIT", "MonsterHunter")
    min_upvotes = int(config.get("MIN_UPVOTES", 100))

    # 1. 爬蟲監控階段
    try:
        update_status("抓取熱門貼文", f"透過 Playwright 掃描 r/{subreddit} 熱門貼文 (門檻 {min_upvotes} 讚)...")
        posts = await fetch_top_reddit_posts(subreddit, min_upvotes=min_upvotes)
    except Exception as e:
        record_error("來源平台爬取階段 (Reddit Scraper)", e)
        return

    # 讀取去重紀錄
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    # 篩選未曾發布過的最新熱門貼文
    candidate = next((p for p in posts if p["id"] not in history), None)
    if not candidate:
        update_status("完成", "目前無符合門檻的新熱門貼文需要發布。", state="SUCCESS")
        return

    update_status("鎖定目標", f"鎖定熱門貼文：[{candidate['id']}] {candidate['title'][:40]}... (👍 {candidate['upvotes']})")

    # 2. AI 中轉站翻譯與遊戲名詞對齊階段
    try:
        update_status("AI 在地化翻譯", f"傳送至 AI 中轉站，目標地區：【{config.get('TARGET_REGION')}】...")
        localized_text = call_ai_proxy(candidate["full_content"], config)
    except Exception as e:
        record_error("AI 中轉站翻譯階段 (AI Brain Proxy)", e)
        return

    # 3. 媒體下載與壓制階段
    media_path = None
    if candidate["media_type"] in ["IMAGE", "VIDEO"]:
        try:
            update_status("媒體處理", f"偵測到 {candidate['media_type']} 媒體，下載並轉碼...")
            media_path = download_media(candidate["media_type"], candidate["media_url"], candidate["id"])
        except Exception as e:
            record_error("媒體下載與音影合成階段 (Media Downloader)", e)
            return

    # 4. Playwright 自動發布階段
    try:
        update_status("Threads 發布", "啟動 Playwright 載入 Session 並自動發布至 Threads...")
        await post_to_threads(localized_text, media_path)
    except Exception as e:
        record_error("Playwright 自動發布階段 (Threads Publisher)", e)
        return

    # 發布成功：寫入去重歷史紀錄
    history.append(candidate["id"])
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    # 標記主控台為正常
    os.makedirs("logs", exist_ok=True)
    with open(ERROR_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "status": "SUCCESS",
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": f"成功發布貼文 [{candidate['id']}] 至 Threads"
        }, f, indent=2, ensure_ascii=False)

    update_status("發布成功", f"貼文 [{candidate['id']}] 已順利同步至 Threads！", state="SUCCESS")
    print("🎉 全流程執行完畢，貼文已成功發布！")

if __name__ == "__main__":
    asyncio.run(main())
