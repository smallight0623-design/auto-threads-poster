import asyncio
import os
import sys
import json
import datetime

sys.path.insert(0, r"C:\Users\d4414\.gemini\antigravity\scratch\auto_threads_poster")
from reddit_scraper import fetch_top_reddit_posts
from bahamut_scraper import fetch_top_bahamut_posts
import rule_engine
import ai_engine
import account_manager
from media_handler import download_media
from threads_playwright import post_to_threads

async def execute_lighthouse_post():
    print("=" * 60)
    print("🚀 啟動【燈塔三：自主在地化搬運與正式發布】實測流程")
    print("=" * 60)

    # 1. 取得帳號設定與 Session
    acc = account_manager.get_account("acc_primary")
    if not acc:
        raise Exception("找不到主要帳號 acc_primary！")
    session_file = account_manager.get_account_session_path("acc_primary")
    if not session_file or not os.path.exists(session_file):
        raise Exception(f"找不到有效 Session 檔案: {session_file}")

    print(f"👤 執行帳號：{acc.get('name')} (ID: acc_primary)")
    print(f"🎯 目標平台：{acc.get('target_platform', 'Threads')}")
    print(f"🔑 Session 狀態：已就緒 ({session_file})")

    # 2. 獲取篩選勝選之素材 (Winner)
    # 優先讀取 lighthouse_test_report.json 中的 selected_winner
    report_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lighthouse_test_report.json")
    winner = None
    if os.path.exists(report_file):
        with open(report_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            winner = data.get("selected_winner")

    if not winner:
        raise Exception("尚未有通過篩選的素材！請先執行篩選。")

    print("\n[階段 1：鎖定搬運素材 (通過燈塔二篩選之首選)]")
    print(f"📌 來源平台：{winner.get('source_platform')}")
    print(f"📌 原始標題：{winner.get('title')}")
    print(f"📌 原始熱度：👍 {winner.get('upvotes')}")
    print(f"📌 原始網址：{winner.get('permalink')}")
    print(f"📌 媒體類型：{winner.get('media_type')}")

    # 3. 燈塔三：在地化翻譯 (純搬運，嚴格不標作者與來源)
    print("\n[階段 2：1:1 道地繁中在地化 (嚴禁標註作者與出處)]")
    global_settings = account_manager.get_global_settings()
    ai_config = {
        "AI_BASE_URL": global_settings.get("AI_BASE_URL"),
        "AI_API_KEY": global_settings.get("AI_API_KEY"),
        "AI_MODEL": global_settings.get("AI_MODEL") or "gemini-2.5-flash",
        "TARGET_REGION": "台灣 (繁體中文)",
        "GAME_NAME": "Monster Hunter Wilds",
        "CUSTOM_TAGS": acc.get("custom_tags", "#魔物獵人荒野 #魔物獵人")
    }

    raw_text = winner.get("full_content") or winner.get("title")
    localized_text = ai_engine.call_ai_proxy(raw_text, ai_config)
    main_text, comment_text = ai_engine.split_post_for_threads(localized_text)
    print(f"📝 在地化主文案 (長度: {len(main_text)})：\n----------------------------------------\n{main_text}\n----------------------------------------")
    if comment_text:
        print(f"💬 在地化留言區續篇 (長度: {len(comment_text)})：\n----------------------------------------\n{comment_text}\n----------------------------------------")

    # 4. 媒體檔案下載與處理
    media_path = None
    if winner.get("media_type") in ["IMAGE", "VIDEO"] and winner.get("media_url"):
        print("\n[階段 3：高畫質媒體下載與檢查]")
        media_path = download_media(winner["media_type"], winner["media_url"], winner["id"])
        print(f"🖼️ 本地媒體檔案：{media_path} (大小: {os.path.getsize(media_path) if media_path and os.path.exists(media_path) else 0} bytes)")

    # 5. Playwright 正式發布至 Threads
    print("\n[階段 4：Playwright 自動化無痕發布至 Threads]")
    await post_to_threads(main_text, media_file_path=media_path, session_file=session_file, comment_text=comment_text)

    # 6. 保存分析與發布記錄
    account_manager.add_account_history("acc_primary", winner["id"])
    account_manager.log_post_analytics("acc_primary", {
        "acc_id": "acc_primary",
        "acc_name": acc.get("name"),
        "post_id": winner["id"],
        "title": winner.get("title", "")[:35],
        "source_platform": winner.get("source_platform", "Reddit"),
        "media_type": winner.get("media_type", "IMAGE"),
        "posted_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "localized_text": localized_text,
        "media_path": media_path
    })

    print("\n" + "=" * 60)
    print("🎉【燈塔三：正式發布驗證完成！】")
    print("✅ 貼文已成功推播至 Threads 帳號。")
    print(f"📸 截圖驗證檔案已保存至 Artifact 目錄。")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(execute_lighthouse_post())
