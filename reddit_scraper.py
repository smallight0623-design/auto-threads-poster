import sys
import asyncio
from playwright.async_api import async_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

async def fetch_top_reddit_posts(subreddit: str, min_upvotes: int = 100, limit: int = 20):
    """
    透過 Playwright 無痕模式採集 Reddit 熱門貼文。
    可 100% 繞過 Reddit 針對 Python requests 的 Cloudflare/網絡安全 403 阻擋。
    """
    url = f"https://www.reddit.com/r/{subreddit}/hot/"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        await page.add_init_script("delete Object.getPrototypeOf(navigator).webdriver")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_selector("shreddit-post", timeout=25000)
        except Exception as e:
            await browser.close()
            raise Exception(f"無法載入 Reddit r/{subreddit} 頁面: {str(e)}")

        raw_posts = await page.eval_on_selector_all(
            "shreddit-post",
            """elements => elements.map(el => {
                const bodyEl = el.querySelector('[slot="text-body"]');
                const postType = (el.getAttribute('post-type') || 'text').toLowerCase();
                const contentHref = el.getAttribute('content-href') || '';
                const permalink = el.getAttribute('permalink') || '';
                
                let mediaType = 'TEXT';
                let mediaUrl = null;

                if (postType === 'video' || contentHref.includes('v.redd.it')) {
                    mediaType = 'VIDEO';
                    mediaUrl = permalink.startsWith('/') ? 'https://reddit.com' + permalink : permalink;
                } else if (contentHref.includes('i.redd.it') || /\\.(jpg|jpeg|png|webp)($|\\?)/i.test(contentHref)) {
                    mediaType = 'IMAGE';
                    mediaUrl = contentHref;
                } else if (postType === 'gallery') {
                    const imgEl = el.querySelector('gallery-carousel img, shreddit-media-lightbox-container img, img[src*="redd.it"]');
                    if (imgEl && imgEl.src) {
                        mediaType = 'IMAGE';
                        mediaUrl = imgEl.src;
                    }
                }

                return {
                    id: el.getAttribute('id') || '',
                    title: el.getAttribute('post-title') || '',
                    score: parseInt(el.getAttribute('score') || '0', 10),
                    post_type: postType,
                    media_type: mediaType,
                    media_url: mediaUrl,
                    body: bodyEl ? bodyEl.innerText.trim() : '',
                    permalink: permalink
                };
            })"""
        )
        await browser.close()

        posts = []
        for p in raw_posts:
            upvotes = p.get("score", 0)
            if upvotes < min_upvotes:
                continue

            clean_id = p["id"].replace("t3_", "")
            permalink = f"https://reddit.com{p['permalink']}" if p['permalink'].startswith("/") else p['permalink']
            full_content = f"{p['title']}\n\n{p['body']}".strip() if p.get("body") else p["title"]

            posts.append({
                "id": clean_id,
                "title": p["title"],
                "full_content": full_content,
                "upvotes": upvotes,
                "media_type": p.get("media_type", "TEXT"),
                "media_url": p.get("media_url"),
                "permalink": permalink
            })

        return posts
