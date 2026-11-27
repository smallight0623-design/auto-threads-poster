import os
import sys
import json
import time
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


def _load_dotenv_if_needed():
    """載入本地 .env（僅在環境變數尚未設定時補齊，不覆蓋 GitHub Secrets）"""
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and not os.getenv(k):
                    os.environ[k] = v
    except Exception:
        pass


def get_taiwan_today_str() -> str:
    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz_tw).strftime("%Y-%m-%d")


def get_kb_path(acc_id: str) -> str:
    acc_dir = os.path.join(BASE_DIR, "accounts", acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    return os.path.join(acc_dir, "viral_knowledge_base.json")


def load_knowledge_base(acc_id: str) -> dict:
    fpath = get_kb_path(acc_id)
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("golden_comments", [])
                data.setdefault("viral_topic_seeds", [])
                data.setdefault("posting_techniques", [])
                data.setdefault("last_learned_at", "")
                data.setdefault("last_learned_date", "")
                return data
        except Exception:
            pass
    return {
        "golden_comments": [],
        "viral_topic_seeds": [],
        "posting_techniques": [],
        "last_learned_at": "",
        "last_learned_date": ""
    }


def save_knowledge_base(acc_id: str, kb: dict):
    fpath = get_kb_path(acc_id)
    # 精煉機制：確保資料庫不被撐爆，最多保留 150 則金句、50 則選題種子、60 條發文技巧
    kb["golden_comments"] = kb.get("golden_comments", [])[-150:]
    kb["viral_topic_seeds"] = kb.get("viral_topic_seeds", [])[-50:]
    kb["posting_techniques"] = kb.get("posting_techniques", [])[-60:]
    kb["last_learned_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    kb["last_learned_date"] = get_taiwan_today_str()
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(kb, f, indent=2, ensure_ascii=False)


def should_run_daily_learning(acc_id: str) -> bool:
    """檢查今日 (台灣時間) 是否尚未執行高強度衝浪學習"""
    kb = load_knowledge_base(acc_id)
    return kb.get("last_learned_date", "") != get_taiwan_today_str()


async def _human_scroll_and_collect(page, target_url: str, label: str, scroll_rounds: int = 4, max_links: int = 10) -> tuple:
    """模擬真實人類滑動瀏覽 Threads 動態並收集貼文全文與互動連結"""
    print(f"🏄 [Threads 衝浪學習] 前往 {label}: {target_url}")
    try:
        await page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(random.uniform(2.5, 4.0))
    except Exception as e:
        print(f"⚠️ [Threads 衝浪學習] {label} 載入警告: {e}")

    collected_snippets = []
    seen_texts = set()
    post_links = []
    seen_links = set()

    for round_idx in range(scroll_rounds):
        batch = await page.evaluate(r'''() => {
            const posts = [];
            const links = [];
            const containers = Array.from(document.querySelectorAll('div[data-pressable-container="true"], article, div[role="article"]'));
            for (const c of containers) {
                const txt = (c.innerText || '').trim();
                if (txt.length >= 20) {
                    posts.push(txt.slice(0, 400));
                }
                const a = c.querySelector('a[href*="/post/"]');
                if (a && a.href) {
                    const m = a.href.match(/(https:\/\/(www\.)?threads\.(net|com)\/@[^\/]+\/post\/[a-zA-Z0-9_\-]+)/);
                    if (m) links.push(m[1].replace('threads.com', 'threads.net'));
                }
            }
            return { posts, links };
        }''')

        for ptxt in batch.get("posts", []):
            key = ptxt[:60]
            if key not in seen_texts:
                seen_texts.add(key)
                collected_snippets.append(ptxt)
        for lnk in batch.get("links", []):
            if lnk not in seen_links:
                seen_links.add(lnk)
                post_links.append(lnk)

        # 模擬人類滾輪滑動與閱讀停頓
        scroll_px = random.randint(550, 950)
        await page.mouse.wheel(0, scroll_px)
        await asyncio.sleep(random.uniform(1.8, 3.4))

    print(f"👀 [{label}] 擬真滑動 {scroll_rounds} 輪，瀏覽 {len(collected_snippets)} 篇貼文，擷取 {len(post_links)} 個貼文連結")
    return collected_snippets, post_links[:max_links]


async def browse_and_extract_threads_discussions(page, keyword: str, max_posts: int = 3) -> list:
    """深入 Threads 瀏覽特定關鍵字，像人類一樣滑貼文並抓取熱門貼文及底下精彩留言"""
    encoded_kw = urllib.parse.quote(keyword)
    search_url = f"https://www.threads.net/search?q={encoded_kw}&serp_type=default"
    _, post_links = await _human_scroll_and_collect(page, search_url, f"關鍵字「{keyword}」", scroll_rounds=3, max_links=max_posts + 3)

    print(f"🔍 [Threads 學習雷達] 深入前 {max_posts} 篇高互動討論串萃取寫法與神回覆...")
    discussions = []

    for p_url in post_links[:max_posts]:
        try:
            print(f"  ➔ 深入閱讀: {p_url}")
            await page.goto(p_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(random.uniform(2.0, 3.5))
            await page.mouse.wheel(0, random.randint(350, 650))
            await asyncio.sleep(random.uniform(1.0, 2.0))

            discussion_data = await page.evaluate(r'''() => {
                const articles = Array.from(document.querySelectorAll('div[data-pressable-container="true"], article, div[role="article"]'));
                if (articles.length === 0) return null;

                const mainPost = articles[0];
                // 保留換行結構以便分析排版格式！
                const mainText = (mainPost.innerText || "").trim().slice(0, 450);

                const comments = [];
                for (let i = 1; i < Math.min(articles.length, 10); i++) {
                    const cText = (articles[i].innerText || "").replace(/\s+/g, ' ').trim();
                    if (cText.length > 3 && cText.length < 220) {
                        comments.push(cText.slice(0, 160));
                    }
                }

                return { mainText, comments };
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


def distill_golden_insights_with_ai(discussions: list, home_feed_samples: list, game_name: str, config: dict) -> dict:
    """
    調用 AI 對採集到的首頁動態與討論串進行深度學習提煉：
    1. 發文技巧與排版格式 (posting_techniques)
    2. 高情商自然神回覆 (golden_comments)
    3. 爆款選題種子 (viral_topic_seeds)
    4. 今日學習過程摘要 (learning_summary)
    """
    if not discussions and not home_feed_samples:
        return {"posting_techniques": [], "golden_comments": [], "viral_topic_seeds": [], "learning_summary": ""}

    base_url = (os.getenv("AI_BASE_URL") or config.get("AI_BASE_URL", "https://api.relayrouter.ai/v1")).rstrip("/")
    api_key = os.getenv("AI_API_KEY") or config.get("AI_API_KEY", "")
    primary_model = os.getenv("AI_MODEL") or config.get("AI_MODEL", "gemini-2.5-flash")

    feed_block = "\n---\n".join(home_feed_samples[:10]) if home_feed_samples else "（無）"
    formatted_samples = []
    for d in discussions:
        s = f"【關鍵字：{d['keyword']}｜原貼文（含換行排版）】：\n{d['main_text']}\n【下方真實留言】：\n"
        for c in d["raw_comments"][:5]:
            s += f"  - {c}\n"
        formatted_samples.append(s)
    disc_block = "\n===\n".join(formatted_samples) if formatted_samples else "（無）"

    prompt = f"""
你是一位專門研究台灣 Threads 演算法與爆紅文案的資深社群操盤手。
今天你像真實人類一樣高強度滑了 Threads 首頁與【{game_name}】相關熱門串，以下是你的真實瀏覽樣本：

【一、Threads 首頁演算法推薦爆文樣本（觀察大家的開頭鉤子與排版格式）】：
{feed_block}

【二、主題討論串與留言區互動實況】：
{disc_block}

【你的深度學習任務】：
1. **發文技巧與格式（posting_techniques）**：觀察首頁與熱門貼文，提煉 2~3 個具體可複製的「開頭第一句鉤子（Hook）、換行排版節奏、互動誘發結構」，說明為什麼這樣寫容易留住人滑下去。
2. **自然回覆神句（golden_comments）**：從留言區挑出 2~4 個「完全沒有 AI 味、自然像真人朋友」的幽默/共鳴回覆，抽象出適用情境與回覆模板。
3. **爆款選題種子（viral_topic_seeds）**：歸納今天大家最熱衷討論的 2~3 個話題焦點與切入角度。
4. **今日學習總結（learning_summary）**：用 2~3 句簡潔白話跟老闆匯報今天滑文的心得與明天發文/回覆的微調建議。

【輸出規格（必須且僅能以 JSON 回傳）】：
{{
  "posting_techniques": [
    {{
      "pattern_name": "技巧名稱 (如：反差吐槽開頭 + 三行留白)",
      "format_example": "排版或句型結構範例",
      "why_it_works": "為什麼演算法跟真人喜歡看 (25字內)"
    }}
  ],
  "golden_comments": [
    {{
      "scenario": "適用情境",
      "quote": "精煉自然回覆",
      "category": "毒舌吐槽 / 自嘲共鳴 / 幽默接梗 / 獵友互助",
      "punchline_power": 9
    }}
  ],
  "viral_topic_seeds": [
    {{
      "topic": "核心選題",
      "why_viral": "爆紅原因",
      "angle": "建議切入角度"
    }}
  ],
  "learning_summary": "給老闆的今日學習過程與明日調整建議（60~120字）"
}}
"""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": primary_model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.35}

    for attempt in range(2):
        try:
            res = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=35)
            if res.status_code == 200:
                import re
                c = res.json()["choices"][0]["message"]["content"]
                match = re.search(r"\{.*\}", c, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
        except Exception as e:
            print(f"⚠️ [AI 提煉異常] 第 {attempt+1} 次嘗試失敗: {e}")
            if attempt == 0:
                time.sleep(2)

    return {"posting_techniques": [], "golden_comments": [], "viral_topic_seeds": [], "learning_summary": ""}


def send_discord_learning_report(webhook_url: str, report: dict) -> bool:
    """將每日 Threads 衝浪學習報告推播到指定的 Discord 頻道"""
    if not webhook_url:
        print("ℹ️ 未設定 DISCORD_WEBHOOK_URL，略過 Discord 推播。")
        return False

    techniques = report.get("new_techniques", [])
    comments = report.get("new_comments", [])
    topics = report.get("new_topics", [])

    tech_lines = []
    for t in techniques[:3]:
        tech_lines.append(f"• **{t.get('pattern_name', '技巧')}**：{t.get('why_it_works', '')}\n  ↳ 範例：`{str(t.get('format_example', ''))[:90]}`")
    tech_text = "\n".join(tech_lines) if tech_lines else "今日持續累積首頁排版樣本中。"

    cmt_lines = []
    for c in comments[:4]:
        cmt_lines.append(f"• 【{c.get('scenario', '情境')}】➔ 「{c.get('quote', '')}」")
    cmt_text = "\n".join(cmt_lines) if cmt_lines else "今日未新增新金句，沿用現有高讚語氣庫。"

    topic_lines = []
    for tp in topics[:3]:
        topic_lines.append(f"• **{tp.get('topic', '')}** — {tp.get('angle', '')}")
    topic_text = "\n".join(topic_lines) if topic_lines else "持續鎖定遊戲社群最新話題。"

    summary = report.get("learning_summary") or "已完成本日高強度滑文與互動語氣觀察，知識庫已同步更新。"

    embed = {
        "title": f"📚 Threads 每日衝浪學習報告（{get_taiwan_today_str()}）",
        "description": f"**今日學習總結**：{summary}",
        "color": 0x5865F2,
        "fields": [
            {
                "name": "🏄 今日擬真衝浪軌跡",
                "value": (
                    f"• 首頁動態瀏覽：**{report.get('home_posts_browsed', 0)}** 篇\n"
                    f"• 主題討論串深讀：**{report.get('discussions_analyzed', 0)}** 串\n"
                    f"• 累計知識庫：**{report.get('total_techniques', 0)}** 條發文技巧 / **{report.get('total_golden_comments', 0)}** 則自然金句"
                ),
                "inline": False
            },
            {
                "name": "✍️ 學到的爆款發文技巧與格式",
                "value": tech_text[:1000],
                "inline": False
            },
            {
                "name": "💬 學到的自然回覆與接梗",
                "value": cmt_text[:1000],
                "inline": False
            },
            {
                "name": "🔥 今日觀察熱門選題",
                "value": topic_text[:1000],
                "inline": False
            }
        ],
        "footer": {
            "text": f"Auto Threads AI 操盤手 ｜ 帳號：{report.get('account_name', 'acc_primary')}"
        }
    }

    try:
        resp = requests.post(webhook_url, json={"embeds": [embed]}, timeout=15)
        if resp.status_code in (200, 204):
            print("✅ [Discord 推播] 每日學習報告已成功送達 Discord 頻道！")
            return True
        else:
            print(f"⚠️ [Discord 推播] 回傳非預期狀態碼 {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ [Discord 推播] 傳送失敗: {e}")
        return False


async def run_daily_threads_learning(acc_id: str = "acc_primary", keywords: list = None, notify_discord: bool = True) -> dict:
    """
    執行每日 Threads 高強度衝浪自主學習巡視：
    1. 像人類一樣滑 Threads 首頁動態 + 關鍵字熱門串
    2. 萃取發文技巧/排版格式、自然回覆神句與爆款選題
    3. 存入知識庫並主動將學習過程回報至 Discord
    """
    _load_dotenv_if_needed()
    acc = account_manager.get_account(acc_id)
    if not acc:
        return {"success": False, "error": f"找不到帳號 {acc_id}"}

    session_file = account_manager.get_account_session_path(acc_id)
    if not session_file or not os.path.exists(session_file):
        return {"success": False, "error": "無有效 session.json"}

    if not keywords:
        keywords = acc.get("comment_keywords") or ["魔物獵人", "MHWilds", "魔物獵人荒野"]

    cfg = account_manager.get_global_settings()
    game_name = acc.get("game_name", "遊戲")

    home_samples = []
    all_discussions = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            storage_state=session_file,
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        await page.add_init_script("delete Object.getPrototypeOf(navigator).webdriver")

        try:
            # 1. 高強度衝浪第一步：像人類一樣滑 Threads 首頁動態，吸收爆款排版與節奏
            home_samples, _ = await _human_scroll_and_collect(
                page, "https://www.threads.net/", "Threads 首頁推薦動態", scroll_rounds=5, max_links=8
            )
            await asyncio.sleep(random.uniform(1.5, 3.0))

            # 2. 高強度衝浪第二步：深入關鍵字討論串看原PO寫法與留言互動
            for kw in keywords[:3]:
                disc = await browse_and_extract_threads_discussions(page, kw, max_posts=2)
                all_discussions.extend(disc)
                await asyncio.sleep(random.uniform(1.5, 2.5))
        finally:
            await browser.close()

    print(f"📊 [學習提煉中] 首頁瀏覽 {len(home_samples)} 篇 ＋ 深入 {len(all_discussions)} 串討論，調用 AI 提煉...")
    distilled = distill_golden_insights_with_ai(all_discussions, home_samples, game_name, cfg)

    kb = load_knowledge_base(acc_id)
    new_techniques = distilled.get("posting_techniques", [])
    new_comments = distilled.get("golden_comments", [])
    new_topics = distilled.get("viral_topic_seeds", [])
    learning_summary = distilled.get("learning_summary", "")

    existing_patterns = set(t.get("pattern_name", "").strip() for t in kb.get("posting_techniques", []))
    for t in new_techniques:
        pn = t.get("pattern_name", "").strip()
        if pn and pn not in existing_patterns:
            t["learned_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            kb["posting_techniques"].append(t)
            existing_patterns.add(pn)

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
    print(f"🎉 [學習完成] 知識庫已更新！技巧: {len(kb['posting_techniques'])} 條，金句: {len(kb['golden_comments'])} 條，選題: {len(kb['viral_topic_seeds'])} 個")

    result = {
        "success": True,
        "account_name": acc.get("name", acc_id),
        "home_posts_browsed": len(home_samples),
        "discussions_analyzed": len(all_discussions),
        "new_techniques_added": len(new_techniques),
        "new_comments_added": len(new_comments),
        "new_topics_added": len(new_topics),
        "total_techniques": len(kb["posting_techniques"]),
        "total_golden_comments": len(kb["golden_comments"]),
        "total_topic_seeds": len(kb["viral_topic_seeds"]),
        "new_techniques": new_techniques,
        "new_comments": new_comments,
        "new_topics": new_topics,
        "learning_summary": learning_summary
    }

    if notify_discord:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        discord_ok = send_discord_learning_report(webhook_url, result)
        result["discord_notified"] = discord_ok

    return result


if __name__ == '__main__':
    res = asyncio.run(run_daily_threads_learning("acc_primary"))
    print("\n學習成果報告:", json.dumps(res, ensure_ascii=False, indent=2))
