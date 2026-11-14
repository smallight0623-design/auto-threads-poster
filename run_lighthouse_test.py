import asyncio
import os
import sys
import json

sys.path.insert(0, r"C:\Users\d4414\.gemini\antigravity\scratch\auto_threads_poster")
from reddit_scraper import fetch_top_reddit_posts
from bahamut_scraper import fetch_top_bahamut_posts
import rule_engine
import ai_engine
import account_manager

async def run_test():
    print("=" * 60)
    print("🚀 啟動【燈塔一 ➔ 燈塔二】現場真實測試流水線")
    print("=" * 60)

    # 1. 採集 (Lighthouse 1: Discovery)
    print("\n[階段 1：自主發現指定主題內容 (Reddit + 巴哈姆特)]")
    raw_posts = []

    # A. Reddit (MonsterHunter Subreddit)
    try:
        print("📡 正在掃描 Reddit r/MonsterHunter (門檻: 100 讚)...")
        r_posts = await fetch_top_reddit_posts("MonsterHunter", min_upvotes=100, sort_type="hot")
        for p in r_posts:
            p["source_platform"] = "Reddit"
            raw_posts.append(p)
        print(f"  ➔ 成功擷取 {len(r_posts)} 篇 Reddit 熱門貼文")
    except Exception as e:
        print(f"  ⚠️ Reddit 擷取異常: {e}")

    # B. 巴哈姆特 (Monster Hunter 哈啦板)
    try:
        print("📡 正在掃描巴哈姆特哈啦板 (門檻: 15 GP)...")
        b_posts = await fetch_top_bahamut_posts("Monster Hunter Wilds", min_gp=15)
        for p in b_posts:
            p["source_platform"] = "巴哈姆特"
            raw_posts.append(p)
        print(f"  ➔ 成功擷取 {len(b_posts)} 篇巴哈姆特熱門貼文")
    except Exception as e:
        print(f"  ⚠️ 巴哈姆特擷取異常: {e}")

    print(f"\n✅ 採集完成，候選池共累積 {len(raw_posts)} 篇潛力素材。")

    # 2. 規則庫過濾 (Lighthouse 2 Gate 1: Transparent Rules)
    print("\n[階段 2：規則庫透明篩選 (rules.json)]")
    passed, rejected, exceptions = rule_engine.filter_candidates(raw_posts)

    print(f"\n📊 篩選分類統計：")
    print(f"  - 通過 (PASS)：{len(passed)} 篇")
    print(f"  - 淘汰 (REJECT)：{len(rejected)} 篇")
    print(f"  - 例外待審 (EXCEPTION)：{len(exceptions)} 篇")

    # 3. 受眾吸引力評選 (Lighthouse 2 Gate 2: Audience Appeal Assessment)
    selected_winner = None
    ai_reason = ""
    if passed:
        print("\n[階段 3：受眾吸引力思維選品 (思考對台灣受眾有沒有吸引力)]")
        global_settings = account_manager.get_global_settings()
        ai_config = {
            "AI_BASE_URL": global_settings.get("AI_BASE_URL"),
            "AI_API_KEY": global_settings.get("AI_API_KEY"),
            "AI_MODEL": global_settings.get("AI_MODEL") or "gemini-2.5-flash",
            "GAME_NAME": "Monster Hunter Wilds"
        }
        if len(passed) > 1:
            selected_winner = ai_engine.select_best_post_material(
                candidates=passed,
                strategy_prompt="先以熱門程度判別，然後思考對於我們受眾有沒有吸引力即可。",
                game_name="Monster Hunter Wilds",
                config=ai_config
            )
            ai_reason = selected_winner.get("curation_reason", "綜合吸引力評定最高")
        else:
            selected_winner = passed[0]
            ai_reason = "唯一通過規則庫之素材"

    # 保存報告
    report_data = {
        "total_scraped": len(raw_posts),
        "passed": passed,
        "rejected": rejected,
        "exceptions": exceptions,
        "selected_winner": selected_winner,
        "ai_reason": ai_reason
    }
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lighthouse_test_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("🎯【最終選拔結果 (The Winner)】")
    if selected_winner:
        print(f"來源平台：{selected_winner.get('source_platform')}")
        print(f"原始標題：{selected_winner.get('title')}")
        print(f"互動數據：👍 {selected_winner.get('upvotes')} (讚/GP/觀看)")
        print(f"媒體類型：{selected_winner.get('media_type')}")
        print(f"AI 吸引力判定理由：{ai_reason}")
    else:
        print("未選出，所有貼文均被淘汰或需要人工審查。")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_test())
