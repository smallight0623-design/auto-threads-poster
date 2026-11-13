import os
import sys
import json
import re
import datetime
import asyncio
from playwright.async_api import async_playwright

import account_manager

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_metrics_file_path(acc_id: str) -> str:
    acc_dir = os.path.join(BASE_DIR, "accounts", acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    return os.path.join(acc_dir, "threads_post_metrics.json")

def load_post_metrics(acc_id: str) -> list:
    fpath = get_metrics_file_path(acc_id)
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_post_metrics(acc_id: str, metrics: list):
    fpath = get_metrics_file_path(acc_id)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

async def scrape_profile_posts_metrics(acc_id: str = "acc_primary", limit: int = 10) -> dict:
    """
    定期（每 2~3 天）巡視個人主頁，精準抓取真實發布反饋：
    👍 讚數、💬 留言數、🔁 轉發數、✈️ 小飛機分享數
    """
    acc = account_manager.get_account(acc_id)
    if not acc:
        return {"success": False, "error": f"找不到帳號 {acc_id}"}

    session_file = os.path.join(BASE_DIR, "accounts", acc_id, "session.json")
    if not os.path.exists(session_file):
        return {"success": False, "error": "無有效 session.json"}

    # 取得個人主頁帳號名稱
    acc_name = acc.get("name", "")
    username = "dinosaur.56467484"
    if "@" in acc_name:
        username = acc_name.split("@")[-1].split()[0].strip()
    elif "." in acc_name:
        username = acc_name.split()[0].strip()

    profile_url = f"https://www.threads.net/@{username}"
    print(f"📊 [成效分析雷達] 前往個人主頁檢測貼文反饋: {profile_url}")

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=session_file,
            viewport={'width': 1280, 'height': 850},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        try:
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(3500)

            posts_raw = await page.evaluate(r'''() => {
                const items = [];
                const articles = Array.from(document.querySelectorAll('div[data-pressable-container="true"], article, div[role="article"]'));
                for (const a of articles) {
                    const link = a.querySelector('a[href*="/post/"]');
                    if (!link) continue;
                    let href = link.href.split('?')[0].replace('threads.com', 'threads.net');
                    
                    // 抓取貼文文字
                    const text = (a.innerText || "").replace(/\s+/g, ' ');

                    // 尋找各項互動指標 (愛心、留言、轉發、飛機)
                    // 在文章內部尋找帶有 aria-label 或 title 的 SVG/按鈕
                    let likes = 0, replies = 0, reposts = 0, shares = 0;
                    
                    // 從整篇文字末尾解析可能出現的數字
                    // 如: "Translate 5" 或 "12 4 1 8"
                    const numbers = text.match(/\d+(\.\d+)?[KM]?/g) || [];

                    items.push({
                        url: href,
                        snippet: text.slice(0, 120),
                        full_text: text,
                        numbers: numbers
                    });
                }
                return items;
            }''')

            print(f"📈 [成效分析雷達] 主頁共探測到 {len(posts_raw)} 篇貼文，深入分析互動數據...")

            # 深入各篇貼文詳情頁抓取更精準的互動列數據
            for p_item in posts_raw[:limit]:
                p_url = p_item["url"]
                try:
                    await page.goto(p_url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(2500)

                    # 抓取詳細數據
                    metrics = await page.evaluate(r'''() => {
                        let likes = 0, replies = 0, reposts = 0, shares = 0;
                        
                        // 1. 抓取按鈕旁的數字
                        const buttons = Array.from(document.querySelectorAll('div[role="button"]'));
                        for (const b of buttons) {
                            const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                            const txt = (b.innerText || '').trim();
                            const num = parseInt(txt) || 0;

                            if (aria.includes('like') || aria.includes('讚')) {
                                likes = num;
                            } else if (aria.includes('reply') || aria.includes('回覆')) {
                                replies = num;
                            } else if (aria.includes('repost') || aria.includes('轉發')) {
                                reposts = num;
                            } else if (aria.includes('share') || aria.includes('分享') || aria.includes('飛機')) {
                                shares = num;
                            }
                        }

                        // 2. 備援：從 Insights 側欄抓取瀏覽量 (若有)
                        let views = 0;
                        const insightsBlock = document.body.innerText;
                        const vMatch = insightsBlock.match(/Views\s*([\d,]+)/i);
                        if (vMatch) {
                            views = parseInt(vMatch[1].replace(/,/g, '')) || 0;
                        }

                        return { likes, replies, reposts, shares, views };
                    }''')

                    post_record = {
                        "url": p_url,
                        "snippet": p_item["snippet"],
                        "likes": metrics.get("likes", 0),
                        "replies": metrics.get("replies", 0),
                        "reposts": metrics.get("reposts", 0),
                        "shares": metrics.get("shares", 0),
                        "views": metrics.get("views", 0),
                        "scraped_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    results.append(post_record)
                    print(f"  貼文: {p_url} ➔ 👍 {post_record['likes']} 讚 | 💬 {post_record['replies']} 則回覆 | 🔁 {post_record['reposts']} 轉發 | ✈️ {post_record['shares']} 分享")
                except Exception as de:
                    print(f"  ⚠️ 詳情探測例外 {p_url}: {de}")
                    continue

        finally:
            await browser.close()

    # 存檔
    save_post_metrics(acc_id, results)
    print(f"✅ [成效分析完成] 已持久化 {len(results)} 篇貼文真實數據至 threads_post_metrics.json")

    return {
        "success": True,
        "scraped_count": len(results),
        "metrics": results
    }

if __name__ == '__main__':
    res = asyncio.run(scrape_profile_posts_metrics("acc_primary", limit=3))
    print("\n抓取成果報告:", json.dumps(res, ensure_ascii=False, indent=2))
