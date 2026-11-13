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
from twitch_scraper import fetch_top_twitch_clips
from ai_engine import call_ai_proxy, select_best_post_material, detect_future_events
from media_handler import download_media
from threads_playwright import post_to_threads
from facebook_playwright import post_to_facebook
import account_manager

ACTIVE_RUNNING_ACCOUNTS = set()

async def run_for_account(acc_id: str, is_fast_track: bool = False):
    """專門為指定的社群帳號工作台執行一次搬運與發布"""
    if acc_id in ACTIVE_RUNNING_ACCOUNTS:
        print(f"⚠️ 帳號工作台 [{acc_id}] 目前已有執行中的發布任務，自動忽略重複觸發！")
        return False

    ACTIVE_RUNNING_ACCOUNTS.add(acc_id)
    try:
        return await _run_for_account_internal(acc_id, is_fast_track=is_fast_track)
    finally:
        ACTIVE_RUNNING_ACCOUNTS.discard(acc_id)

async def _run_for_account_internal(acc_id: str, is_fast_track: bool = False):
    account = account_manager.get_account(acc_id)
    if not account:
        print(f"❌ 找不到帳號 ID: {acc_id}")
        return False

    if is_fast_track and not account_manager.is_fast_track_allowed(acc_id):
        print(f"[{acc_id}][Fast-Track] 距離上次發布未滿安全冷卻期，跳過此次快速巡航以防風控。")
        return True

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

    # 1. 跨平台多來源雷達監控階段
    raw_posts = []
    source_platforms = account.get("source_platforms") or [account.get("source_platform", "Reddit")]
    strategy_prompt = account.get("strategy_prompt", "")

    for src in source_platforms:
        src_name = src.strip()
        try:
            if src_name.lower() == "threads":
                account_manager.update_account_status(acc_id, "雷達掃描", f"正在掃描 Threads [{game_name}] 爆文 (門檻 {min_upvotes} 讚)...")
                p_list = await fetch_top_threads_posts(game_name, min_likes=min_upvotes, session_file=session_path)
            elif "x" in src_name.lower() or "twitter" in src_name.lower():
                account_manager.update_account_status(acc_id, "雷達掃描", f"正在掃描 X (Twitter) [{game_name}] 即時推文 (門檻 {min_upvotes} 讚)...")
                x_session = os.path.join(os.path.dirname(session_path), "x_session.json") if session_path else "x_session.json"
                if not os.path.exists(x_session) and os.path.exists("x_session.json"):
                    x_session = "x_session.json"
                p_list = await fetch_top_x_tweets(game_name, min_likes=min_upvotes, session_file=x_session, sort_recent=(discovery_mode == "rising"))
            elif "巴哈" in src_name or "bahamut" in src_name.lower():
                account_manager.update_account_status(acc_id, "雷達掃描", f"正在掃描巴哈姆特哈啦板 [{game_name}] 本土爆文 (門檻 {min_upvotes} GP)...")
                p_list = await fetch_top_bahamut_posts(subreddit or game_name, min_gp=min_upvotes)
            elif "twitch" in src_name.lower():
                account_manager.update_account_status(acc_id, "雷達掃描", f"正在掃描 Twitch 熱門短片 [{game_name}] (門檻 {min_upvotes} 觀看)...")
                p_list = fetch_top_twitch_clips(game_name, min_views=min_upvotes)
            else: # 預設 Reddit
                mode_desc = "潛力榜 (Rising)" if discovery_mode == "rising" else "熱門榜 (Hot)"
                account_manager.update_account_status(acc_id, "雷達掃描", f"正在掃描 Reddit r/{subreddit} {mode_desc} (門檻 {min_upvotes} 讚)...")
                p_list = await fetch_top_reddit_posts(subreddit, min_upvotes=min_upvotes, sort_type=discovery_mode)

            for p in p_list:
                p["source_platform"] = src_name
                raw_posts.append(p)
        except Exception as e:
            print(f"[{acc_id}] 來源平台 {src_name} 抓取警告: {e}")

    # 一葉知秋：AI 背景嗅探未來重大事件時間線索
    try:
        discovered_events = detect_future_events(raw_posts, game_name, ai_config)
        for disc in discovered_events:
            account_manager.add_discovered_milestone(acc_id, disc)
            print(f"💡 [{acc_id}][Event Horizon] 探測到未來重大事件線索：【{disc.get('title')}】({disc.get('target_date')})")
    except Exception as e:
        pass

    # 2. 去重檢查與破裂級爆款過濾
    history = account_manager.get_account_history(acc_id)
    available_candidates = [p for p in raw_posts if p["id"] not in history]

    if is_fast_track:
        fast_threshold = int(account.get("fast_track_min_upvotes") or 300)
        available_candidates = [p for p in available_candidates if p.get("upvotes", 0) >= fast_threshold]
        if not available_candidates:
            print(f"[{acc_id}][Fast-Track] 未發現超過破裂級門檻 (≥{fast_threshold} 讚) 之爆款，維持原定巡航排程。")
            return True
        print(f"🚨 [{acc_id}][Fast-Track] 發現 {len(available_candidates)} 篇破裂級超速爆文！打破常規排程提前插隊發布！")

    if not available_candidates:
        account_manager.update_account_status(acc_id, "完成", "目前各來源平台無符合門檻之全新未發布貼文。", state="SUCCESS")
        account_manager.mark_account_run_completed(acc_id)
        return True

    # 3. 戰役階段分析與 AI 流量總監智慧「選材評估」階段
    campaign_status = account_manager.get_account_campaign_status(acc_id)
    if campaign_status and campaign_status.get("phase") != "CRUISE":
        print(f"🎯 [{acc_id}] 戰役階段生效：{campaign_status.get('badge_text')}")

    if len(available_candidates) > 1:
        account_manager.update_account_status(acc_id, "AI 選材評估", f"AI 流量總監正在依據戰役策略評選最佳爆款 ({len(available_candidates)} 篇候選)...")
        candidate = select_best_post_material(available_candidates, strategy_prompt, game_name, ai_config, campaign_status=campaign_status)
    else:
        candidate = available_candidates[0]

    # 立即預約鎖定候選貼文至歷史清單，杜絕任何重複發布可能
    account_manager.add_account_history(acc_id, candidate["id"])

    curation_note = f" (理由: {candidate.get('curation_reason')})" if candidate.get('curation_reason') else ""
    account_manager.update_account_status(acc_id, "鎖定目標", f"鎖定 [{candidate.get('source_platform')}] 爆文：{candidate['title'][:35]}... (👍 {candidate['upvotes']}){curation_note}")

    # 4. AI 1:1 道地翻譯 (嚴格不改動內容、不標作者、在地遊戲譯名)
    try:
        account_manager.update_account_status(acc_id, "AI 道地翻譯", f"傳送至 AI 執行 1:1 忠實翻譯，目標語言：【{account.get('target_region')}】...")
        localized_text = call_ai_proxy(candidate["full_content"], ai_config)
    except Exception as e:
        account_manager.record_account_error(acc_id, "AI 翻譯階段 (AI Brain Proxy)", e)
        return False
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

    # 成功寫入去重歷史、成效情報日誌並推算下一次巡航時間
    account_manager.add_account_history(acc_id, candidate["id"])
    account_manager.log_post_analytics(acc_id, {
        "acc_id": acc_id,
        "acc_name": acc_name,
        "post_id": candidate["id"],
        "title": candidate.get("title", ""),
        "source_platform": candidate.get("source_platform", ""),
        "target_platform": target_platform,
        "upvotes": candidate.get("upvotes", 0),
        "media_type": candidate.get("media_type", "TEXT"),
        "curation_reason": candidate.get("curation_reason", ""),
        "is_fast_track": is_fast_track,
        "campaign_phase": campaign_status.get("phase", "CRUISE")
    })
    account_manager.mark_account_run_completed(acc_id)
    track_badge = " [🚨爆款自主插隊]" if is_fast_track else ""
    account_manager.update_account_status(acc_id, "發布成功", f"貼文 [{candidate['id']}]{track_badge} 已順利同步至 {target_platform}！", state="SUCCESS")
    print(f"🎉 帳號【{acc_name}】在 {target_platform}{track_badge} 任務圓滿完成！")
    return True

async def main():
    parser = argparse.ArgumentParser(description="多帳號熱文自動搬運系統")
    parser.add_argument("--account", type=str, help="指定單一帳號 ID 執行發布")
    parser.add_argument("--all", action="store_true", help="依序執行所有啟用的帳號工作台")
    parser.add_argument("--fast-track", action="store_true", help="以破裂級爆款自主插隊模式掃描執行")
    parser.add_argument("--patrol", action="store_true", help="執行指定帳號的 Threads 留言區海巡獲客")
    args = parser.parse_args()

    if args.patrol:
        import threads_commenter
        target_acc = args.account or "acc_primary"
        print(f"💬 [Main CLI] 啟動帳號【{target_acc}】Threads 海巡獲客留言...")
        res = await threads_commenter.run_threads_patrol_async(target_acc)
        print("海巡結果:", json.dumps(res, ensure_ascii=False, indent=2))
        return

    if args.account:
        await run_for_account(args.account, is_fast_track=args.fast_track)
    else:
        # 預設執行所有已啟用的帳號
        accounts = account_manager.get_accounts()
        enabled_accounts = [a for a in accounts if a.get("enabled", True)]
        
        if not enabled_accounts:
            print("目前沒有已啟用的帳號工作台需要執行。")
            return

        print(f"共發現 {len(enabled_accounts)} 個已啟用的帳號工作台，開始批次排隊執行...")
        for acc in enabled_accounts:
            await run_for_account(acc["id"], is_fast_track=args.fast_track)
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
