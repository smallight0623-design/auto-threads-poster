import os
import sys
import argparse
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
import account_manager

async def run_for_account(acc_id: str):
    """專門為指定的社群帳號工作台執行一次搬運與發布"""
    account = account_manager.get_account(acc_id)
    if not account:
        print(f"❌ 找不到帳號 ID: {acc_id}")
        return False

    acc_name = account.get("name", acc_id)
    print(f"\n==================================================")
    print(f"🚀 開始執行帳號工作台：【{acc_name}】 (ID: {acc_id})")
    print(f"==================================================")

    account_manager.update_account_status(acc_id, "初始化", "正在檢查帳號 Session 與工作台設定...")

    session_path = account_manager.get_account_session_path(acc_id)
    if not session_path:
        err = Exception("此工作台尚未設定或匯入 Threads Cookie Session，請先在主控台貼入 Session！")
        account_manager.record_account_error(acc_id, "Session 檢查", err)
        return False

    global_settings = account_manager.get_global_settings()
    ai_config = {
        "AI_BASE_URL": global_settings.get("AI_BASE_URL"),
        "AI_API_KEY": global_settings.get("AI_API_KEY"),
        "AI_MODEL": global_settings.get("AI_MODEL"),
        "TARGET_REGION": account.get("target_region", "台灣 (繁體中文)"),
        "GAME_NAME": account.get("game_name", "遊戲")
    }

    subreddit = account.get("subreddit", "MonsterHunter")
    min_upvotes = int(account.get("min_upvotes", 100))

    # 1. 爬蟲監控階段
    try:
        account_manager.update_account_status(acc_id, "抓取熱門貼文", f"透過 Playwright 掃描 r/{subreddit} 熱門貼文 (門檻 {min_upvotes} 讚)...")
        posts = await fetch_top_reddit_posts(subreddit, min_upvotes=min_upvotes)
    except Exception as e:
        account_manager.record_account_error(acc_id, "來源平台爬取階段 (Reddit Scraper)", e)
        return False

    # 2. 去重檢查
    history = account_manager.get_account_history(acc_id)
    candidate = next((p for p in posts if p["id"] not in history), None)
    if not candidate:
        account_manager.update_account_status(acc_id, "完成", "目前無符合門檻的新熱門貼文需要發布。", state="SUCCESS")
        return True

    account_manager.update_account_status(acc_id, "鎖定目標", f"鎖定熱門貼文：[{candidate['id']}] {candidate['title'][:40]}... (👍 {candidate['upvotes']})")

    # 3. AI 中轉站翻譯階段
    try:
        account_manager.update_account_status(acc_id, "AI 在地化翻譯", f"傳送至 AI 中轉站，目標地區：【{account.get('target_region')}】...")
        localized_text = call_ai_proxy(candidate["full_content"], ai_config)
    except Exception as e:
        account_manager.record_account_error(acc_id, "AI 中轉站翻譯階段 (AI Brain Proxy)", e)
        return False

    # 4. 媒體下載階段
    media_path = None
    if candidate["media_type"] in ["IMAGE", "VIDEO"]:
        try:
            account_manager.update_account_status(acc_id, "媒體處理", f"偵測到 {candidate['media_type']} 媒體，下載並轉碼...")
            media_path = download_media(candidate["media_type"], candidate["media_url"], candidate["id"])
        except Exception as e:
            account_manager.record_account_error(acc_id, "媒體下載與音影合成階段 (Media Downloader)", e)
            return False

    # 5. Playwright 發布階段
    try:
        account_manager.update_account_status(acc_id, "Threads 發布", "啟動 Playwright 載入此帳號專屬 Session 並自動發布至 Threads...")
        await post_to_threads(localized_text, media_path, session_file=session_path)
    except Exception as e:
        account_manager.record_account_error(acc_id, "Playwright 自動發布階段 (Threads Publisher)", e)
        return False

    # 成功寫入去重歷史
    account_manager.add_account_history(acc_id, candidate["id"])
    account_manager.update_account_status(acc_id, "發布成功", f"貼文 [{candidate['id']}] 已順利同步至 Threads！", state="SUCCESS")
    print(f"🎉 帳號【{acc_name}】任務圓滿完成！")
    return True

async def main():
    parser = argparse.ArgumentParser(description="多帳號熱文自動搬運系統")
    parser.add_argument("--account", type=str, help="指定單一帳號 ID 執行發布")
    parser.add_argument("--all", action="store_true", help="依序執行所有啟用的帳號工作台")
    args = parser.parse_args()

    if args.account:
        await run_for_account(args.account)
    else:
        # 預設執行所有已啟用的帳號
        accounts = account_manager.get_accounts()
        enabled_accounts = [a for a in accounts if a.get("enabled", True)]
        
        if not enabled_accounts:
            print("目前沒有已啟用的帳號工作台需要執行。")
            return

        print(f"共發現 {len(enabled_accounts)} 個已啟用的帳號工作台，開始批次排隊執行...")
        for acc in enabled_accounts:
            await run_for_account(acc["id"])
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
