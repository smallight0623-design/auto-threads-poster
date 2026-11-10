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

async def post_to_threads(text: str, media_file_path: str = None, session_file: str = "threads_session.json"):
    """
    透過 Playwright 自動載入 Cookie Session，發布文字與本地媒體檔案至 Threads
    """
    username = os.getenv("THREADS_USERNAME", "")
    password = os.getenv("THREADS_PASSWORD", "")
    session_env = os.getenv("THREADS_SESSION_DATA", "")

    if session_env and not os.path.exists(session_file):
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(session_env)

    storage_state = session_file if os.path.exists(session_file) else None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage"
            ]
        )

        context = await browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("正在打開 Threads 首頁...")
        await page.goto("https://www.threads.net/", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        # 檢驗登入狀態
        is_login_page = "login" in page.url or await page.locator("input[name='username']").count() > 0
        if is_login_page:
            print("檢測到未登入，嘗試使用帳號密碼登入...")
            if not username or not password:
                await browser.close()
                raise Exception("Threads 未處於登入狀態，且未提供帳密或有效 Session Cookie！請先在主控台匯入 Session。")

            await page.goto("https://www.threads.net/login")
            await page.fill("input[placeholder*='用戶名稱'], input[name='username']", username)
            await page.fill("input[type='password']", password)
            await page.click("div[role='button']:has-text('登入'), div[role='button']:has-text('Log in')")
            
            try:
                await page.wait_for_url("https://www.threads.net/", timeout=25000)
            except Exception:
                await browser.close()
                raise Exception("帳密登入超時！可能觸發了 Meta 安全驗證碼 (Captcha/SMS)。強烈建議使用主控台匯入本機登入後的 Session Cookie。")

        # 尋找並點擊可見的發文入口（優先尋找 aria-label="New thread" 等可見按鈕）
        print("尋找可見的發文按鈕 (New thread / What's new)...")
        trigger_selectors = [
            "[aria-label*='New thread']:visible",
            "[aria-label*='new thread']:visible",
            "[aria-label*='建立']:visible",
            "[aria-label*='Create']:visible",
            "text='What’s new?':visible",
            "text='What\\'s new?':visible",
            "text='有什麼新動態？':visible",
            "div[role='button']:has-text('New thread'):visible"
        ]

        create_btn = None
        for sel in trigger_selectors:
            loc = page.locator(sel)
            if await loc.count() > 0:
                for i in range(await loc.count()):
                    item = loc.nth(i)
                    if await item.is_visible():
                        create_btn = item
                        break
            if create_btn:
                break

        if not create_btn:
            await browser.close()
            raise Exception("在 Threads 首頁找不到可見的發文入口按鈕，可能頁面尚未完全載入或 Cookie 已失效。")

        await create_btn.click()
        await asyncio.sleep(2)

        # 鎖定發文彈跳對話框 (Dialog)
        dialog = page.locator("div[role='dialog']").first
        await dialog.wait_for(state="visible", timeout=12000)

        # 定位輸入框並填入文案
        editor = dialog.locator("div[contenteditable='true']").first
        await editor.wait_for(state="visible", timeout=8000)
        await editor.click()
        await editor.fill(text)
        print("文案已輸入完畢！")
        await asyncio.sleep(1)

        # 若有媒體檔案，注入本地檔案
        if media_file_path and os.path.exists(media_file_path):
            print(f"正在上傳本地媒體：{media_file_path}")
            file_input = dialog.locator("input[type='file']").first
            await file_input.set_input_files(media_file_path)
            
            # 等待 Threads 網頁渲染轉碼
            print("等待媒體解析與預覽處理 (8秒)...")
            await asyncio.sleep(8)

        # 鎖定真正的 Post 送出按鈕 (精確匹配文字，排除 Post options 等其他按鈕)
        print("尋找真正的 Post 發布按鈕 (exact match)...")
        post_btn = dialog.get_by_role("button", name="Post", exact=True).or_(
            dialog.locator("div[role='button']:text-is('Post')")
        ).or_(
            dialog.locator("div[role='button']:text-is('發佈')")
        ).or_(
            dialog.locator("div[role='button']:text-is('Đăng')")
        ).first

        if not await post_btn.is_visible():
            await browser.close()
            raise Exception("找不到發布送出按鈕 (Post)，文案或媒體可能未通過前端驗證。")

        await post_btn.click()
        print("已點擊 Post 按鈕，等待貼文送出並確認對話框關閉...")
        
        try:
            await dialog.wait_for(state="hidden", timeout=18000)
            print("✅ Dialog 對話框已關閉，貼文已正式發布至 Threads！")
        except Exception:
            print("⚠️ Dialog 未自動關閉，正在等待後台同步...")
            await asyncio.sleep(6)

        await browser.close()
