import sys
import urllib.parse
import asyncio
from playwright.async_api import async_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

async def fetch_top_threads_posts(query: str, min_likes: int = 50, session_file: str = "threads_session.json", sort_recent: bool = False):
    """
    透過 Playwright 採集 Threads 上的熱門/即時貼文。
    可做為 Facebook 帳號發文時的優質外部來源 (符合跨平台避開原則)。
    """
    encoded_query = urllib.parse.quote(query)
    filter_param = "&filter=recent" if sort_recent else ""
    url = f"https://www.threads.net/search?q={encoded_query}{filter_param}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        
        # 嘗試載入 session（若存在）
        context_kwargs = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "viewport": {"width": 1920, "height": 1080}
        }
        import os
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
            raise Exception(f"無法載入 Threads 搜尋頁面: {str(e)}")

        raw_posts = await page.eval_on_selector_all(
            "div[data-pressable-container='true']",
            """containers => containers.map((c, idx) => {
                // 內文節點
                const textNodes = c.querySelectorAll('span[dir="auto"]');
                let rawLines = Array.from(textNodes).map(s => s.innerText.trim()).filter(Boolean);
                
                // 去除純數字 (讚數/轉發數) 與常見頭部
                let contentLines = rawLines.filter(line => !/^\\d+$/.test(line) && !line.includes('•') && line.length > 1);

                // 媒體檢測
                const img = c.querySelector('img[src*="cdninstagram"], img[src*="fbcdn"]');
                const video = c.querySelector('video[src]');
                let mediaType = 'TEXT';
                let mediaUrl = null;
                if (video && video.src) {
                    mediaType = 'VIDEO';
                    mediaUrl = video.src;
                } else if (img && img.src && !img.src.includes('profile')) {
                    mediaType = 'IMAGE';
                    mediaUrl = img.src;
                }

                // 讚數分析
                const buttons = c.querySelectorAll('div[role="button"]');
                let likes = 0;
                for (const b of buttons) {
                    const txt = b.innerText.trim();
                    if (/^\\d+(\\.\\d+)?[kKmM]?$/.test(txt)) {
                        let multiplier = 1;
                        if (txt.toLowerCase().includes('k')) multiplier = 1000;
                        if (txt.toLowerCase().includes('m')) multiplier = 1000000;
                        likes = Math.round(parseFloat(txt) * multiplier);
                        break;
                    }
                }

                // 貼文連結與 ID
                const link = c.querySelector('a[href*="/post/"]') || c.querySelector('a[href*="/@"]');
                const permalink = link ? link.href : '';

                return {
                    id: permalink ? ('th_' + permalink.split('/').filter(Boolean).pop()) : ('th_post_' + idx),
                    content: contentLines.join('\\n'),
                    mediaType,
                    mediaUrl,
                    likes,
                    permalink
                };
            })"""
        )
        await browser.close()

        posts = []
        for p in raw_posts:
            if not p.get("content"):
                continue
            if p.get("likes", 0) < min_likes:
                continue

            posts.append({
                "id": p["id"],
                "title": p["content"].split("\n")[0][:60],
                "full_content": p["content"],
                "upvotes": p["likes"],
                "media_type": p["mediaType"],
                "media_url": p["mediaUrl"],
                "permalink": p["permalink"],
                "source_platform": "Threads"
            })

        return posts
