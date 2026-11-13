import os
import sys
import json
import random
import urllib.parse
import datetime
import asyncio
from playwright.async_api import async_playwright
import requests

import account_manager

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_kb_path(acc_id: str) -> str:
    acc_dir = os.path.join(BASE_DIR, "accounts", acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    return os.path.join(acc_dir, "viral_knowledge_base.json")

def load_knowledge_base(acc_id: str) -> dict:
    fpath = get_kb_path(acc_id)
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "golden_comments": [],
        "viral_topic_seeds": [],
        "last_learned_at": ""
    }

def save_knowledge_base(acc_id: str, kb: dict):
    fpath = get_kb_path(acc_id)
    # 精煉機制：確保資料庫不被撐爆，最多保留 150 則金句、50 則選題種子
    kb["golden_comments"] = kb.get("golden_comments", [])[-150:]
    kb["viral_topic_seeds"] = kb.get("viral_topic_seeds", [])[-50:]
    kb["last_learned_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(kb, f, indent=2, ensure_ascii=False)

async def browse_and_extract_threads_discussions(page, keyword: str, max_posts: int = 3) -> list:
    """
    深入 Threads 瀏覽特定關鍵字，抓取熱門貼文以及底下的精彩留言
    """
    encoded_kw = urllib.parse.quote(keyword)
    search_url = f"https://www.threads.net/search?q={encoded_kw}&serp_type=default"
    print(f"📖 [Threads 學習雷達] 正在搜尋話題「{keyword}」: {search_url}")
    
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(3500)
    except Exception as e:
        print(f"⚠️ [Threads 學習雷達] 搜尋頁載入警告: {e}")

    # 取得熱門貼文連結清單
    post_links = await page.evaluate(r'''() => {
        const links = [];
        const seen = new Set();
        const allA = Array.from(document.querySelectorAll('a[href*="/post/"]'));
        for (const a of allA) {
            let href = a.href;
            const match = href.match(/(https:\/\/(www\.)?threads\.(net|com)\/@[^\/]+\/post\/[a-zA-Z0-9_\-]+)/);
            if (!match) continue;
            const clean = match[1].replace('threads.com', 'threads.net');
            if (!seen.has(clean)) {
                seen.add(clean);
                links.push(clean);
            }
        }
        return links;
    }''')

    print(f"🔍 [Threads 學習雷達] 找到 {len(post_links)} 篇討論，深入前 {max_posts} 篇萃取高讚對話...")
    discussions = []

    for p_url in post_links[:max_posts]:
        try:
            print(f"  ➔ 深入探訪: {p_url}")
            await page.goto(p_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)

            # 抓取該貼文主文與下方留言清單
            discussion_data = await page.evaluate(r'''() => {
                // 抓取第一篇主文內容
                const articles = Array.from(document.querySelectorAll('div[data-pressable-container="true"], article, div[role="article"]'));
                if (articles.length === 0) return null;

                const mainPost = articles[0];
                const mainText = (mainPost.innerText || "").replace(/\s+/g, ' ').slice(0, 250);

                // 抓取底下的留言 (其餘 articles)
                const comments = [];
                for (let i = 1; i < Math.min(articles.length, 8); i++) {
                    const cText = (articles[i].innerText || "").replace(/\s+/g, ' ').trim();
                    if (cText.length > 3 && cText.length < 200) {
                        comments.push(cText.slice(0, 150));
                    }
                }

                return {
                    mainText,
                    comments
                };
            }''')

            if discussion_data and discussion_data.get("mainText"):
                discussions.append({
                    "url": p_url,
                    "keyword": keyword,
                    "main_text": discussion_data["mainText"],
                    "raw_comments": discussion_data.get("comments", [])
                })
        except Exception as pe:
            print(f"  ⚠️ 探訪貼文 {p_url} 例外: {pe}")
            continue

    return discussions

def distill_golden_insights_with_ai(discussions: list, game_name: str, config: dict) -> dict:
    """
    調用 AI 對採集到的社群發文與回覆進行提煉：
    過濾廢話，挑選真正具備「高情商、幽默、神回覆、引發瘋傳」的金句與選題靈感
    """
    if not discussions:
        return {"golden_comments": [], "viral_topic_seeds": []}

    base_url = (config.get("AI_BASE_URL", "https://api.relayrouter.ai/v1")).rstrip("/")
    api_key = config.get("AI_API_KEY", "")
    primary_model = config.get("AI_MODEL", "gemini-2.5-flash")

    formatted_samples = []
    for d in discussions:
        s = f"【原貼文】：{d['main_text']}\n【下方真實留言】：\n"
        for c in d["raw_comments"][:4]:
            s += f"  - {c}\n"
        formatted_samples.append(s)

    combined_text = "\n---\n".join(formatted_samples)

    prompt = f"""
你是一位專門分析社群演算法與爆款梗的資深分析師。以下是今天從 Threads 官方搜尋採集到的【{game_name}】真實熱門貼文與下方網友留言：

{combined_text}

【你的提煉任務】：
1. 找出網友留言中「極度幽默、中肯吐槽、引發共鳴、或神級接梗」的黃金神回覆（Golden Punchlines）。
   - 請將每一條神回覆抽象出「適用情境（Scenario）」，這樣未來我們遇到同類貼文時可以直接照抄或融會貫通。
   - 拒絕任何無意義表情符號、廣告或廢話。
2. 提煉今天這個主題最引發討論的「爆款選題種子（Viral Topic Seeds）」，指出大家今天都在吵什麼、關注什麼點。

【輸出規格（必須且僅能以 JSON 回傳）】：
{{
  "golden_comments": [
    {{
      "scenario": "適用情境 (如：當玩家抱怨武器傷害低 / 隊友貓車 / 遊戲太肝時)",
      "quote": "精煉神回覆 (如：正常，這遊戲魔物打你是黑魂，你打魔物是修腳)",
      "category": "毒舌吐槽 / 自嘲共鳴 / 幽默接梗 / 獵友互助",
      "punchline_power": 9
    }}
  ],
  "viral_topic_seeds": [
    {{
      "topic": "今天大家熱烈討論的核心選題",
      "why_viral": "為什麼這能引爆流量與留言",
      "angle": "建議搬運或發文的切入角度"
    }}
  ]
}}
"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": primary_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4
    }

    try:
        res = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=25)
        if res.status_code == 200:
            import re
            c = res.json()["choices"][0]["message"]["content"]
            match = re.search(r"\{.*\}", c, re.DOTALL)
            if match:
                return json.loads(match.group(0))
    except Exception as e:
        print(f"⚠️ [AI 提煉異常] {e}")

    return {"golden_comments": [], "viral_topic_seeds": []}

async def run_daily_threads_learning(acc_id: str = "acc_primary", keywords: list = None) -> dict:
    """
    執行每日 Threads 自主學習巡視：
    1. 瀏覽 Threads 熱門討論
    2. 萃取神回覆與爆款選題
    3. 自動精煉存入知識庫
    """
    acc = account_manager.get_account(acc_id)
    if not acc:
        return {"success": False, "error": f"找不到帳號 {acc_id}"}

    session_file = os.path.join(BASE_DIR, "accounts", acc_id, "session.json")
    if not os.path.exists(session_file):
        return {"success": False, "error": "無有效 session.json"}

    if not keywords:
        keywords = acc.get("comment_keywords") or ["魔物獵人", "MHWilds", "荒野"]

    cfg = account_manager.get_global_settings()
    game_name = acc.get("game_name", "遊戲")

    all_discussions = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=session_file,
            viewport={'width': 1280, 'height': 850},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        try:
            for kw in keywords[:3]:
                disc = await browse_and_extract_threads_discussions(page, kw, max_posts=2)
                all_discussions.extend(disc)
                await asyncio.sleep(2)
        finally:
            await browser.close()

    print(f"📊 [學習提煉中] 共採集到 {len(all_discussions)} 串討論，調用 AI 萃取黃金金句...")
    distilled = distill_golden_insights_with_ai(all_discussions, game_name, cfg)

    # 存入知識庫
    kb = load_knowledge_base(acc_id)
    new_comments = distilled.get("golden_comments", [])
    new_topics = distilled.get("viral_topic_seeds", [])

    existing_quotes = set(c.get("quote", "").strip() for c in kb.get("golden_comments", []))
    for item in new_comments:
        q = item.get("quote", "").strip()
        if q and q not in existing_quotes:
            item["learned_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            kb["golden_comments"].append(item)
            existing_quotes.add(q)

    existing_topics = set(t.get("topic", "").strip() for t in kb.get("viral_topic_seeds", []))
    for t in new_topics:
        tp = t.get("topic", "").strip()
        if tp and tp not in existing_topics:
            t["learned_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            kb["viral_topic_seeds"].append(t)
            existing_topics.add(tp)

    save_knowledge_base(acc_id, kb)
    print(f"🎉 [學習完成] 知識庫已更新！現有黃金金句: {len(kb['golden_comments'])} 條，選題靈感: {len(kb['viral_topic_seeds'])} 個")

    return {
        "success": True,
        "new_comments_added": len(new_comments),
        "new_topics_added": len(new_topics),
        "total_golden_comments": len(kb["golden_comments"]),
        "total_topic_seeds": len(kb["viral_topic_seeds"])
    }

if __name__ == '__main__':
    res = asyncio.run(run_daily_threads_learning("acc_primary"))
    print("\n學習成果報告:", json.dumps(res, ensure_ascii=False, indent=2))
