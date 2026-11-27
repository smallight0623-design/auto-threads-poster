import os
import sys
import asyncio
from playwright.async_api import async_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

async def post_to_facebook(text: str, media_path: str = None, session_file: str = "facebook_session.json", is_headless: bool = True):
    """
    透過 Playwright 自動載入 Session Cookie 並發布貼文至 Facebook。
    支援純文字、高畫質相片、影片自動上傳。
    """
    if not os.path.exists(session_file):
        raise FileNotFoundError(f"找不到 Facebook Session 檔案：{session_file}，請先執行登入工具匯入 Cookie！")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=is_headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-notifications"
            ]
        )
        context = await browser.new_context(
            storage_state=session_file,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        page = await context.new_page()
        await page.add_init_script("delete Object.getPrototypeOf(navigator).webdriver")

        print("正在載入 Facebook 首頁...")
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # 檢查是否被登出或導向登入頁
        if "login" in page.url:
            await browser.close()
            raise Exception("Facebook Session 已失效或過期，請重新使用小工具登入 Facebook！")

        print("正在定位 Facebook 發文框 (在想些什麼？)...")
        # 尋找發文按鈕觸發器
        composer_trigger = page.locator(
            "div[role='button']:has-text('在想些什麼？'), "
            "div[role='button']:has-text('在想些什麼'), "
            "div[role='button']:has-text(\"What's on your mind\"), "
            "[aria-label*='在想些什麼'], "
            "[aria-label*=\"What's on your mind\"]"
        ).first

        try:
            await composer_trigger.wait_for(state="visible", timeout=15000)
            await composer_trigger.click()
        except Exception:
            # 備援：嘗試捲動後再次尋找
            await page.keyboard.press("PageDown")
            await page.wait_for_timeout(1000)
            await composer_trigger.click()

        print("等待發文彈窗 (Dialog) 出現...")
        dialog = page.locator("div[role='dialog']").first
        await dialog.wait_for(state="visible", timeout=15000)

        # 定位輸入框 (contenteditable 或 role=textbox)
        print("正在填入發文文案...")
        textbox = dialog.locator("div[role='textbox'], div[contenteditable='true']").first
        await textbox.wait_for(state="visible", timeout=10000)
        await textbox.click()

        # 分行輸入或聚焦後貼上，保留原有換行與排版
        # 在 Windows 上使用 fill 或直接鍵盤輸入
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line:
                await page.keyboard.type(line)
            if i < len(lines) - 1:
                await page.keyboard.down("Shift")
                await page.keyboard.press("Enter")
                await page.keyboard.up("Shift")
        
        await page.wait_for_timeout(1000)

        # 若有圖片或影片，進行上傳
        if media_path and os.path.exists(media_path):
            print(f"正在附加多媒體檔案：{media_path} ...")
            # 尋找檔案上傳 input
            file_input = dialog.locator("input[type='file'][accept*='image'], input[type='file'][accept*='video']").first
            
            # 若 dialog 內尚未渲染 input[type=file]，點擊「相片/影片」按鈕喚醒它
            if await file_input.count() == 0:
                photo_btn = dialog.locator(
                    "[aria-label*='相片/影片'], "
                    "[aria-label*='相片'], "
                    "[aria-label*='Photo/video'], "
                    "div[role='button']:has-text('相片/影片')"
                ).first
                if await photo_btn.count() > 0:
                    await photo_btn.click()
                    await page.wait_for_timeout(1500)
            
            file_input = dialog.locator("input[type='file']").first
            await file_input.set_input_files(os.path.abspath(media_path))
            print("等待媒體檔案處理與縮圖就緒...")
            await page.wait_for_timeout(5000)

        # 定位「發佈」按鈕
        print("正在點擊【發佈】提交按鈕...")
        submit_btn = dialog.locator(
            "div[aria-label='發佈'][role='button'], "
            "div[aria-label='發布'][role='button'], "
            "div[aria-label='Post'][role='button'], "
            "div[role='button']:has-text('發佈'), "
            "div[role='button']:has-text('發布'), "
            "div[role='button']:has-text('Post')"
        ).first

        await submit_btn.wait_for(state="visible", timeout=10000)
        
        # 確保按鈕不是 disabled
        for _ in range(10):
            is_disabled = await submit_btn.get_attribute("aria-disabled")
            if is_disabled != "true":
                break
            await page.wait_for_timeout(500)

        await submit_btn.click()

        # 等待彈窗消失
        print("等待發佈完成...")
        try:
            await dialog.wait_for(state="hidden", timeout=25000)
        except Exception:
            # 部分情況下 dialog 關閉較慢，等待網絡閒置
            await page.wait_for_timeout(5000)

        print("🎉 Facebook 貼文已成功發布！")
        await browser.close()
        return True


async def post_to_facebook_group(group_url: str, text: str, media_path: str = None, session_file: str = "facebook_session.json", is_headless: bool = True) -> dict:
    """
    透過 Playwright 自動導航至指定 Facebook 社團並發布差異化商品圖文，
    嘗試擷取貼文永久連結 (permalink) 回傳以供後續留言自動巡檢回覆使用。
    """
    import account_manager
    resolved_session = account_manager.materialize_session_file(
        session_file, "FACEBOOK_SESSION_DATA", "facebook_session.json"
    )
    if not resolved_session or not os.path.exists(resolved_session):
        raise FileNotFoundError(f"找不到有效 Facebook Session（{session_file} / FACEBOOK_SESSION_DATA）！")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=is_headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-notifications"]
        )
        context = await browser.new_context(
            storage_state=resolved_session,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        page = await context.new_page()
        await page.add_init_script("delete Object.getPrototypeOf(navigator).webdriver")

        print(f"📡 [FB 社團發文] 正在載入指定社團: {group_url}")
        await page.goto(group_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3500)

        if "login" in page.url:
            await browser.close()
            raise Exception("Facebook Session 已失效或過期，請重新匯入 Facebook Cookie！")

        # 定位社團內的發文觸發器（「留個言吧...」/「建立公開貼文...」/「Write something...」）
        trigger = page.locator(
            "div[role='button']:has-text('留個言吧'), "
            "div[role='button']:has-text('建立公開貼文'), "
            "div[role='button']:has-text('Write something'), "
            "div[role='button']:has-text('販售商品'), "
            "[aria-label*='留個言吧'], "
            "[aria-label*='Write something']"
        ).first

        await trigger.wait_for(state="visible", timeout=15000)
        await trigger.click()

        dialog = page.locator("div[role='dialog']").first
        await dialog.wait_for(state="visible", timeout=15000)

        textbox = dialog.locator("div[role='textbox'], div[contenteditable='true']").first
        await textbox.wait_for(state="visible", timeout=10000)
        await textbox.click()

        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line:
                await page.keyboard.type(line, delay=15)
            if i < len(lines) - 1:
                await page.keyboard.down("Shift")
                await page.keyboard.press("Enter")
                await page.keyboard.up("Shift")
        await page.wait_for_timeout(1000)

        if media_path and os.path.exists(media_path):
            print(f"🖼️ [FB 社團發文] 正在附加商品圖片: {media_path}")
            file_input = dialog.locator("input[type='file'][accept*='image'], input[type='file'][accept*='video']").first
            if await file_input.count() == 0:
                photo_btn = dialog.locator(
                    "[aria-label*='相片/影片'], [aria-label*='相片'], [aria-label*='Photo/video'], div[role='button']:has-text('相片/影片')"
                ).first
                if await photo_btn.count() > 0:
                    await photo_btn.click()
                    await page.wait_for_timeout(1500)
            file_input = dialog.locator("input[type='file']").first
            await file_input.set_input_files(os.path.abspath(media_path))
            await page.wait_for_timeout(5000)

        submit_btn = dialog.locator(
            "div[aria-label='發佈'][role='button'], div[aria-label='發布'][role='button'], div[aria-label='Post'][role='button'], "
            "div[role='button']:has-text('發佈'), div[role='button']:has-text('發布'), div[role='button']:has-text('Post')"
        ).first
        await submit_btn.wait_for(state="visible", timeout=10000)
        for _ in range(10):
            if await submit_btn.get_attribute("aria-disabled") != "true":
                break
            await page.wait_for_timeout(500)

        await submit_btn.click()
        try:
            await dialog.wait_for(state="hidden", timeout=25000)
        except Exception:
            await page.wait_for_timeout(4000)

        # 嘗試重新整理並抓取最新一篇屬於我方文案片段的貼文 permalink
        permalink = group_url
        try:
            await page.wait_for_timeout(3000)
            snippet = text.splitlines()[0][:18]
            found_link = await page.evaluate(r'''(snip) => {
                const arts = Array.from(document.querySelectorAll('div[role="article"]'));
                for (const a of arts) {
                    if ((a.innerText || '').includes(snip)) {
                        const lnk = a.querySelector('a[href*="/posts/"], a[href*="/permalink/"]');
                        if (lnk && lnk.href) return lnk.href.split('?')[0];
                    }
                }
                return '';
            }''', snippet)
            if found_link:
                permalink = found_link
        except Exception:
            pass

        print(f"🎉 [FB 社團發文] 成功發布至社團！貼文連結: {permalink}")
        await browser.close()
        return {"success": True, "permalink": permalink, "group_url": group_url}

