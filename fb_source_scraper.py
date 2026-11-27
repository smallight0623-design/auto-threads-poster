import os
import sys
import hashlib
import asyncio
from playwright.async_api import async_playwright

import account_manager

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


async def fetch_top_facebook_posts(target_urls: list, session_file: str = "facebook_session.json", limit: int = 10) -> list:
    """
    透過 Playwright 載入 Facebook Session，抓取指定公開社團或粉絲專頁的近期圖文貼文，
    供 Threads 搬運與在地化翻譯使用。
    """
    resolved_session = account_manager.materialize_session_file(
        session_file, "FACEBOOK_SESSION_DATA", "facebook_session.json"
    )
    if not resolved_session or not os.path.exists(resolved_session):
        print("ℹ️ [FB 採集器] 尚未設定有效的 Facebook Session，略過 FB 來源抓取。")
        return []

    if not target_urls:
        return []

    posts = []
    seen_hashes = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-notifications"]
        )
        context = await browser.new_context(
            storage_state=resolved_session,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        page = await context.new_page()
        await page.add_init_script("delete Object.getPrototypeOf(navigator).webdriver")

        try:
            for url in target_urls:
                if len(posts) >= limit:
                    break
                try:
                    print(f"📡 [FB 採集器] 正在掃描來源頁面: {url}")
                    await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    await asyncio.sleep(3.5)

                    if "login" in page.url:
                        print("⚠️ [FB 採集器] Facebook Session 已失效，跳過此來源。")
                        break

                    # 向下微幅捲動觸發動態渲染
                    await page.mouse.wheel(0, 900)
                    await asyncio.sleep(2)

                    extracted = await page.evaluate(r'''() => {
                        const results = [];
                        const articles = Array.from(document.querySelectorAll('div[role="article"]'));
                        for (const art of articles) {
                            const msgEl = art.querySelector('div[data-ad-preview="message"], div[dir="auto"]');
                            const rawText = msgEl ? (msgEl.innerText || '').trim() : (art.innerText || '').trim();
                            if (rawText.length < 15) continue;

                            let mediaType = 'TEXT';
                            let mediaUrl = null;
                            const imgEl = art.querySelector('img[src*="scontent"]');
                            if (imgEl && imgEl.src && imgEl.width >= 200) {
                                mediaType = 'IMAGE';
                                mediaUrl = imgEl.src;
                            }

                            const linkEl = art.querySelector('a[href*="/posts/"], a[href*="/permalink/"]');
                            const permalink = linkEl ? linkEl.href.split('?')[0] : '';

                            results.push({
                                text: rawText.slice(0, 1200),
                                mediaType,
                                mediaUrl,
                                permalink
                            });
                            if (results.length >= 8) break;
                        }
                        return results;
                    }''')

                    for item in extracted:
                        txt = item.get("text", "").strip()
                        if not txt:
                            continue
                        digest = hashlib.md5(txt[:120].encode("utf-8")).hexdigest()[:12]
                        if digest in seen_hashes:
                            continue
                        seen_hashes.add(digest)

                        first_line = txt.splitlines()[0][:60]
                        posts.append({
                            "id": f"fb_{digest}",
                            "title": first_line,
                            "full_content": txt,
                            "upvotes": 50 if item.get("mediaType") == "IMAGE" else 25,
                            "replies_count": 0,
                            "media_type": item.get("mediaType", "TEXT"),
                            "media_url": item.get("mediaUrl"),
                            "permalink": item.get("permalink") or url,
                            "source_platform": "Facebook"
                        })
                        if len(posts) >= limit:
                            break
                except Exception as ue:
                    print(f"⚠️ [FB 採集器] 掃描 {url} 發生警告: {ue}")
        finally:
            await browser.close()

    print(f"✅ [FB 採集器] 成功採集 {len(posts)} 篇 FB 貼文素材！")
    return posts[:limit]
