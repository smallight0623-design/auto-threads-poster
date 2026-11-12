import sys
import os
import urllib.parse
import asyncio
from playwright.async_api import async_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

async def fetch_top_x_tweets(query: str, min_likes: int = 50, session_file: str = "x_session.json", sort_recent: bool = False):
    """
    透過 Playwright 載入 X (Twitter) Session Cookie 採集最新爆款推文。
    可做為 Threads / Facebook 帳號發文時的高速外部策源地。
    """
    encoded_query = urllib.parse.quote(query)
    filter_param = "&f=live" if sort_recent else ""
    url = f"https://x.com/search?q={encoded_query}{filter_param}"

    async with async_playwright() as p:
        launch_kwargs = {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ],
            "ignore_default_args": ["--enable-automation"]
        }
        try:
            browser = await p.chromium.launch(channel="chrome", **launch_kwargs)
        except Exception:
            browser = await p.chromium.launch(**launch_kwargs)
        
        context_kwargs = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "viewport": {"width": 1920, "height": 1080}
        }
        if session_file and os.path.exists(session_file):
            context_kwargs["storage_state"] = session_file

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()
        await page.add_init_script("delete Object.getPrototypeOf(navigator).webdriver")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(3500)
        except Exception as e:
            await browser.close()
            raise Exception(f"無法載入 X (Twitter) 搜尋頁面: {str(e)}")

        # 檢查是否被重導至登入頁
        if "login" in page.url:
            await browser.close()
            raise Exception("X (Twitter) 需要登入 Cookie 才能檢視推文！請先執行桌面【取得 X (Twitter) 登入 Cookie】小工具。")

        raw_tweets = await page.eval_on_selector_all(
            "article[data-testid='tweet']",
            """tweets => tweets.map((t, idx) => {
                const textEl = t.querySelector('[data-testid=\"tweetText\"]');
                const fullText = textEl ? textEl.innerText.trim() : '';

                // 媒體檢測
                const img = t.querySelector('[data-testid=\"tweetPhoto\"] img');
                const video = t.querySelector('video[src]');
                let mediaType = 'TEXT';
                let mediaUrl = null;

                if (video && video.src) {
                    mediaType = 'VIDEO';
                    mediaUrl = video.src;
                } else if (img && img.src) {
                    mediaType = 'IMAGE';
                    mediaUrl = img.src;
                }

                // 讚數
                const likeBtn = t.querySelector('[data-testid=\"like\"]');
                let likes = 0;
                if (likeBtn) {
                    const txt = likeBtn.innerText.trim();
                    if (/^\\d+(\\.\\d+)?[kKmM]?$/.test(txt)) {
                        let multiplier = 1;
                        if (txt.toLowerCase().includes('k')) multiplier = 1000;
                        if (txt.toLowerCase().includes('m')) multiplier = 1000000;
                        likes = Math.round(parseFloat(txt) * multiplier);
                    }
                }

                // 連結與 ID
                const link = t.querySelector('a[href*=\"/status/\"]');
                const permalink = link ? ('https://x.com' + link.getAttribute('href')) : '';
                const tweetId = permalink ? ('x_' + permalink.split('/status/').pop().split('?')[0]) : ('x_tweet_' + idx);

                return {
                    id: tweetId,
                    content: fullText,
                    mediaType,
                    mediaUrl,
                    likes,
                    permalink
                };
            })"""
        )
        await browser.close()

        posts = []
        for t in raw_tweets:
            if not t.get("content"):
                continue
            if t.get("likes", 0) < min_likes:
                continue

            posts.append({
                "id": t["id"],
                "title": t["content"].split("\n")[0][:60],
                "full_content": t["content"],
                "upvotes": t["likes"],
                "media_type": t["mediaType"],
                "media_url": t["mediaUrl"],
                "permalink": t["permalink"],
                "source_platform": "X (Twitter)"
            })

        return posts
