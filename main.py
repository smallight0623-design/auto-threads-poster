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
from ai_engine import call_ai_proxy, select_best_post_material, detect_future_events, split_post_for_threads
from media_handler import download_media
from threads_playwright import post_to_threads
from facebook_playwright import post_to_facebook
import account_manager
import content_queue

ACTIVE_RUNNING_ACCOUNTS = set()

async def run_patrol_task(acc_id: str, account: dict):
    """執行自動巡航獲客留言 (AI 社群推銷員)"""
    if not account.get("comment_agent_enabled", True):
        return
    try:
        import threads_commenter
        max_cmt = int(account.get("comment_single_limit") or 2)
        print(f"\n💬 [{acc_id}] 啟動 Threads 自動巡航獲客留言 (單次上限: {max_cmt} 則)...")
        patrol_res = await threads_commenter.run_threads_patrol_async(acc_id, max_comments=max_cmt)
        comments_sent = patrol_res.get("commented_count", 0)
        print(f"[{acc_id}] 🎯 Threads 海巡獲客週期完成：成功發布 {comments_sent} 則留言")
    except Exception as e:
        print(f"⚠️ [{acc_id}] Threads 海巡獲客執行異常: {e}")

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
    campaign_status = account.get("campaign_status") or {}

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
                baha_threshold = min(int(min_upvotes or 100), 20)
                account_manager.update_account_status(acc_id, "雷達掃描", f"正在掃描巴哈姆特哈啦板 [{game_name}] 本土爆文 (門檻 {baha_threshold} GP)...")
                p_list = await fetch_top_bahamut_posts(subreddit or game_name, min_gp=baha_threshold)
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


    # 2. 去重檢查與破裂級爆款過濾 (雙重校驗：帳號發布歷史 + 全局一週去重緩存)
    history = set(account_manager.get_account_history(acc_id))
    available_candidates = [p for p in raw_posts if p["id"] not in history and not content_queue.is_already_posted(p["id"])]

    if is_fast_track:
        fast_threshold = int(account.get("fast_track_min_upvotes") or 300)
        available_candidates = [p for p in available_candidates if p.get("upvotes", 0) >= fast_threshold]
        if not available_candidates:
            print(f"[{acc_id}][Fast-Track] 未發現超過破裂級門檻 (≥{fast_threshold} 讚) 之爆款，維持原定巡航排程。")
            return True
        print(f"🚨 [{acc_id}][Fast-Track] 發現 {len(available_candidates)} 篇破裂級超速爆文！打破常規排程提前插隊發布！")

    passed_candidates = []
    if available_candidates:
        # 3. 規則庫透明篩選與例外標註 (Rule Engine - 燈塔二)
        import rule_engine
        account_manager.update_account_status(acc_id, "規則篩選", f"正在依據 rules.json 審查 {len(available_candidates)} 篇候選貼文...")
        passed_candidates, rejected_candidates, exception_candidates = rule_engine.filter_candidates(available_candidates)

        if passed_candidates:
            added_count = content_queue.enqueue_candidates(passed_candidates, set(history))
            print(f"[{acc_id}] 📥 已將 {added_count} 篇優質素材匯入 200 篇容量儲備庫 (目前庫存: {len(content_queue.load_queue())} 篇)")
    else:
        print(f"[{acc_id}] ℹ️ 本次來源平台暫無全新未發布貼文，直接由 200 篇素材儲備庫挑選排程文章發布。")

    # 4. 時段智慧選品：無論本次有無抓到新文章，均從 200 篇素材庫中挑選最適合當前時段之熱門/攻略素材
    candidate = content_queue.pop_next_post_for_slot()
    if not candidate:
        if passed_candidates:
            candidate = passed_candidates[0]
        else:
            msg = "素材庫與當前候選均無可用素材，等待下一次巡航。"
            print(f"[{acc_id}] ⚠️ {msg}")
            account_manager.update_account_status(acc_id, "完成", msg, state="SUCCESS")
            account_manager.mark_account_run_completed(acc_id)
            if account.get("comment_agent_enabled", True) and not is_fast_track:
                await run_patrol_task(acc_id, account)
            return True

    # 立即預約鎖定候選貼文至歷史清單，杜絕任何重複發布可能
    account_manager.add_account_history(acc_id, candidate["id"])
    content_queue.record_posted_id(candidate["id"])

    prio_tag = " [🔥 建設性攻略/實用乾貨]" if candidate.get("is_priority_guide") else ""
    account_manager.update_account_status(acc_id, "鎖定目標", f"鎖定 [{candidate.get('source_platform')}]{prio_tag}：{candidate['title'][:35]}... (👍 {candidate['upvotes']})")

    # 4. AI 1:1 道地翻譯 (純搬運，嚴格不改動內容、不標作者、在地遊戲譯名)
    try:
        account_manager.update_account_status(acc_id, "AI 道地翻譯", f"傳送至 AI 執行 1:1 忠實翻譯，目標語言：【{account.get('target_region')}】...")
        raw_text = candidate.get("full_content") or candidate.get("title")
        localized_text = call_ai_proxy(raw_text, ai_config)
    except Exception as e:
        account_manager.record_account_error(acc_id, "AI 翻譯階段 (AI Brain Proxy)", e)
        return False

    # 智慧長文分段：主內文 + 留言區續篇
    main_text, comment_text = split_post_for_threads(localized_text)

    # 4. 媒體下載階段
    media_path = None
    if candidate.get("media_type") in ["IMAGE", "VIDEO"] and candidate.get("media_url"):
        try:
            account_manager.update_account_status(acc_id, "媒體處理", f"偵測到 {candidate['media_type']} 媒體，下載並轉碼...")
            media_path = download_media(candidate["media_type"], candidate["media_url"], candidate["id"])
        except Exception as e:
            account_manager.record_account_error(acc_id, "媒體下載與音影合成階段 (Media Downloader)", e)
            return False

    # 5. Playwright 發布階段 (分流 Threads 與 Facebook，Threads 支援長文留言續篇)
    try:
        if target_platform.lower() == "facebook":
            account_manager.update_account_status(acc_id, "Facebook 發布", "啟動 Playwright 載入 Facebook Session 並自動發布至動態牆...")
            await post_to_facebook(main_text, media_path, session_file=session_path)
        else:
            account_manager.update_account_status(acc_id, "Threads 發布", "啟動 Playwright 載入 Threads Session 並自動發布至 Threads...")
            await post_to_threads(main_text, media_path, session_file=session_path, comment_text=comment_text)
    except Exception as e:
        account_manager.record_account_error(acc_id, f"Playwright 自動發布階段 ({target_platform} Publisher)", e)
        return False

    # 成功寫入去重歷史、成效情報日誌並推算下一次巡航時間
    account_manager.add_account_history(acc_id, candidate["id"])
    content_queue.record_posted_id(candidate["id"])
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

    # 6. 自動巡航獲客留言 (AI 社群推銷員)
    if account.get("comment_agent_enabled", True) and not is_fast_track:
        await run_patrol_task(acc_id, account)

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
