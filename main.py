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
from threads_scraper import fetch_top_threads_posts
from x_scraper import fetch_top_x_tweets
from bahamut_scraper import fetch_top_bahamut_posts
from ai_engine import call_ai_proxy
from media_handler import download_media
from threads_playwright import post_to_threads
from facebook_playwright import post_to_facebook
import account_manager

ACTIVE_RUNNING_ACCOUNTS = set()

async def run_for_account(acc_id: str):
    """專門為指定的社群帳號工作台執行一次搬運與發布"""
    if acc_id in ACTIVE_RUNNING_ACCOUNTS:
        print(f"⚠️ 帳號工作台 [{acc_id}] 目前已有執行中的發布任務，自動忽略重複觸發！")
        return False

    ACTIVE_RUNNING_ACCOUNTS.add(acc_id)
    try:
        return await _run_for_account_internal(acc_id)
    finally:
        ACTIVE_RUNNING_ACCOUNTS.discard(acc_id)

async def _run_for_account_internal(acc_id: str):
    account = account_manager.get_account(acc_id)
    if not account:
        print(f"❌ 找不到帳號 ID: {acc_id}")
        return False

    acc_name = account.get("name", acc_id)
    target_platform = account.get("target_platform", "Threads")
    source_platform = account.get("source_platform", "Reddit")
    discovery_mode = account.get("discovery_mode", "rising")
    game_name = account.get("game_name", "遊戲")
    subreddit = account.get("subreddit", "MonsterHunter")
    min_upvotes = int(account.get("min_upvotes", 100))

    # 跨平台搬運互斥原則：如果發布目標是 Threads，絕不從 Threads 搬運；若目標是 Facebook，絕不從 Facebook 搬運
    if target_platform.lower() == "threads" and source_platform.lower() == "threads":
        source_platform = "Reddit"
    elif target_platform.lower() == "facebook" and source_platform.lower() == "facebook":
        source_platform = "Reddit"

    print(f"\n==================================================")
    print(f"🚀 開始執行帳號工作台：【{acc_name}】 (ID: {acc_id})")
    print(f"🎯 目標平台：{target_platform} ｜ 📡 來源雷達：{source_platform} ({discovery_mode})")
    print(f"==================================================")

    account_manager.update_account_status(acc_id, "初始化", f"正在檢查 {target_platform} Session 與工作台設定...")

    session_path = account_manager.get_account_session_path(acc_id)
    if not session_path:
        err = Exception(f"此工作台尚未設定或匯入 {target_platform} Cookie Session，請先在主控台貼入 Session！")
        account_manager.record_account_error(acc_id, "Session 檢查", err)
        return False

    global_settings = account_manager.get_global_settings()
    ai_config = {
        "AI_BASE_URL": global_settings.get("AI_BASE_URL"),
        "AI_API_KEY": global_settings.get("AI_API_KEY"),
        "AI_MODEL": global_settings.get("AI_MODEL"),
        "TARGET_REGION": account.get("target_region", "台灣 (繁體中文)"),
        "GAME_NAME": game_name,
        "CUSTOM_TAGS": account.get("custom_tags", "")
    }

    # 1. 爬蟲監控階段 (依據來源平台與發現模式)
    try:
        posts = []
        if source_platform.lower() == "threads":
            account_manager.update_account_status(acc_id, "抓取熱門貼文", f"透過 Playwright 搜尋 Threads [{game_name}] 爆文 (門檻 {min_upvotes} 讚)...")
            posts = await fetch_top_threads_posts(game_name, min_likes=min_upvotes, session_file=session_path)
        elif "x" in source_platform.lower() or "twitter" in source_platform.lower():
            account_manager.update_account_status(acc_id, "抓取熱門貼文", f"透過 Playwright 搜尋 X (Twitter) [{game_name}] 即時推文 (門檻 {min_upvotes} 讚)...")
            x_session = os.path.join(os.path.dirname(session_path), "x_session.json") if session_path else "x_session.json"
            if not os.path.exists(x_session) and os.path.exists("x_session.json"):
                x_session = "x_session.json"
            posts = await fetch_top_x_tweets(game_name, min_likes=min_upvotes, session_file=x_session, sort_recent=(discovery_mode == "rising"))
        elif "巴哈" in source_platform or "bahamut" in source_platform.lower():
            account_manager.update_account_status(acc_id, "抓取熱門貼文", f"正在抓取巴哈姆特哈啦板 [{game_name}] 台灣本土爆文 (門檻 {min_upvotes} GP)...")
            posts = await fetch_top_bahamut_posts(subreddit or game_name, min_gp=min_upvotes)
        else: # 預設 Reddit
            mode_desc = "剛爆發潛力榜 (Rising)" if discovery_mode == "rising" else "成熟熱門榜 (Hot)"
            account_manager.update_account_status(acc_id, "抓取熱門貼文", f"透過 Playwright 掃描 Reddit r/{subreddit} {mode_desc} (門檻 {min_upvotes} 讚)...")
            posts = await fetch_top_reddit_posts(subreddit, min_upvotes=min_upvotes, sort_type=discovery_mode)
    except Exception as e:
        account_manager.record_account_error(acc_id, f"來源平台爬取階段 ({source_platform} Scraper)", e)
        return False

    # 2. 去重檢查
    history = account_manager.get_account_history(acc_id)
    candidate = next((p for p in posts if p["id"] not in history), None)
    if not candidate:
        account_manager.update_account_status(acc_id, "完成", "目前無符合門檻的新熱門貼文需要發布。", state="SUCCESS")
        return True

    # 立即預約鎖定候選貼文至歷史清單，杜絕任何重複發布可能
    account_manager.add_account_history(acc_id, candidate["id"])

    account_manager.update_account_status(acc_id, "鎖定目標", f"鎖定熱門貼文：[{candidate['id']}] {candidate['title'][:40]}... (👍 {candidate['upvotes']})")

    # 3. AI 中轉站翻譯與風格重塑 (不標作者、1:1 格式、在地專有名詞)
    try:
        account_manager.update_account_status(acc_id, "AI 在地化翻譯", f"傳送至 AI 中轉站，目標地區：【{account.get('target_region')}】...")
        localized_text = call_ai_proxy(candidate["full_content"], ai_config)
    except Exception as e:
        account_manager.record_account_error(acc_id, "AI 中轉站翻譯階段 (AI Brain Proxy)", e)
        return False

    # 4. 媒體下載階段
    media_path = None
    if candidate.get("media_type") in ["IMAGE", "VIDEO"] and candidate.get("media_url"):
        try:
            account_manager.update_account_status(acc_id, "媒體處理", f"偵測到 {candidate['media_type']} 媒體，下載並轉碼...")
            media_path = download_media(candidate["media_type"], candidate["media_url"], candidate["id"])
        except Exception as e:
            account_manager.record_account_error(acc_id, "媒體下載與音影合成階段 (Media Downloader)", e)
            return False

    # 5. Playwright 發布階段 (分流 Threads 與 Facebook)
    try:
        if target_platform.lower() == "facebook":
            account_manager.update_account_status(acc_id, "Facebook 發布", "啟動 Playwright 載入 Facebook Session 並自動發布至動態牆...")
            await post_to_facebook(localized_text, media_path, session_file=session_path)
        else:
            account_manager.update_account_status(acc_id, "Threads 發布", "啟動 Playwright 載入 Threads Session 並自動發布至 Threads...")
            await post_to_threads(localized_text, media_path, session_file=session_path)
    except Exception as e:
        account_manager.record_account_error(acc_id, f"Playwright 自動發布階段 ({target_platform} Publisher)", e)
        return False

    # 成功寫入去重歷史
    account_manager.add_account_history(acc_id, candidate["id"])
    account_manager.update_account_status(acc_id, "發布成功", f"貼文 [{candidate['id']}] 已順利同步至 {target_platform}！", state="SUCCESS")
    print(f"🎉 帳號【{acc_name}】在 {target_platform} 任務圓滿完成！")
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
