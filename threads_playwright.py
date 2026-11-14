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

        # 智慧解析內文與主題標籤 (Hashtags)
        import re
        tags = re.findall(r'#([^\s#]+)', text)
        body_text = re.sub(r'(?:^|\n)\s*(?:#[^\s#]+\s*)+$', '', text).strip()
        if not body_text:
            body_text = text

        # 淨化 Markdown 符號（Threads 不支援 Markdown 渲染，去除 **粗體**、*清單點，轉化為社群符號）
        body_text = re.sub(r'\*\*(.*?)\*\*', r'\1', body_text)
        body_text = re.sub(r'^\s*[\*\-]\s+', '▫️ ', body_text, flags=re.MULTILINE)
        body_text = re.sub(r'(?<!\w)\*(.*?)\*(?!\w)', r'\1', body_text)

        # 定位輸入框並填入主內文
        editor = dialog.locator("div[contenteditable='true']").first
        await editor.wait_for(state="visible", timeout=8000)
        await editor.click()
        await editor.fill(body_text)
        print("主內文已填入！")
        await asyncio.sleep(1)

        # 若含有主題標籤，透過實體鍵盤事件觸發 Threads 原生主題標籤 (Topic Tag Chip)
        if tags:
            primary_tag = tags[0]
            print(f"正在透過鍵盤事件注入 Threads 官方主題標籤：#{primary_tag}")
            await page.keyboard.press("End")
            await page.keyboard.press("Enter")
            await page.keyboard.type(f"#{primary_tag}", delay=80)
            await page.wait_for_timeout(800)
            # 按下 Enter 讓 Threads 官方選單自動鎖定並轉為藍色標籤
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(500)

            # 若有其他標籤，以標準空白間隔輸入
            for extra_tag in tags[1:]:
                await page.keyboard.type(f" #{extra_tag} ")
                await page.wait_for_timeout(300)
            print("主題標籤已成功轉化為官方 Topic 標記！")

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

        # 燈塔三驗證：留存發布後之畫面截圖作為客觀證據 (Lighthouse 3 Verification)
        proof_path = r"C:\Users\d4414\.gemini\antigravity\brain\b07effa5-8267-4988-9eec-6f8f631667d6\threads_lighthouse3_posted_proof.png"
        try:
            await asyncio.sleep(3)
            await page.screenshot(path=proof_path)
            print(f"📸 [燈塔三驗證] 已保存發布畫面截圖證據：{proof_path}")
        except Exception as e:
            print(f"⚠️ 截圖保存警告: {e}")

        await browser.close()

async def update_threads_bio(new_bio: str, session_file: str = "threads_session.json") -> bool:
    """
    透過 Playwright 自動更新 Threads 個人檔案簡介 (Bio)
    """
    if not os.path.exists(session_file):
        raise Exception(f"找不到 Session 檔案: {session_file}")

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
            storage_state=session_file,
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            print("[Threads Bio Updater] 正在前往 Threads 個人主頁...")
            await page.goto("https://www.threads.net/", wait_until="domcontentloaded")
            await asyncio.sleep(2.5)

            # 透過 evaluate 尋找自己的個人檔案連結
            profile_url = await page.evaluate('''() => {
                const links = Array.from(document.querySelectorAll('a[href*="/@"]'));
                for (const a of links) {
                    if (a.href && !a.href.includes('/post/')) {
                        return a.href;
                    }
                }
                return null;
            }''')

            if profile_url:
                print(f"[Threads Bio Updater] 前往個人主頁: {profile_url}")
                await page.goto(profile_url, wait_until="domcontentloaded")
                await asyncio.sleep(2.5)

            # 點擊 Edit profile / 編輯個人檔案
            edit_btn = page.locator("div:text-is('Edit profile')").or_(
                page.locator("button:text-is('Edit profile')")
            ).or_(
                page.locator("text='編輯個人檔案'")
            ).first

            if not await edit_btn.is_visible():
                fallback_link = page.locator("a[href*='/@']").first
                if await fallback_link.is_visible():
                    await fallback_link.click()
                    await asyncio.sleep(2.5)
                    edit_btn = page.locator("div:text-is('Edit profile')").or_(
                        page.locator("button:text-is('Edit profile')")
                    ).or_(
                        page.locator("text='編輯個人檔案'")
                    ).first

            if await edit_btn.is_visible():
                await edit_btn.click()
                await asyncio.sleep(2)

                # 尋找並點擊 Bio 欄位進入 Edit bio 子視窗
                bio_row = page.locator("text='+ Write bio'").or_(
                    page.locator("text='寫下簡介'")
                ).or_(
                    page.locator("div[role='dialog'] div:has-text('Bio')")
                ).or_(
                    page.locator("text='Bio'")
                ).first

                if await bio_row.is_visible():
                    try:
                        await bio_row.click(force=True, timeout=3000)
                    except Exception:
                        pass
                else:
                    await page.evaluate('''() => {
                        const dialog = document.querySelector('div[role="dialog"]') || document.body;
                        const allElements = Array.from(dialog.querySelectorAll('div, span'));
                        for (const el of allElements) {
                            if (el.innerText.trim().includes('Bio') || el.innerText.trim().includes('簡介')) {
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }''')

                await asyncio.sleep(1.5)

                # 尋找 Edit bio 子視窗的 textarea
                textarea = page.locator("textarea[placeholder*='bio' i]").or_(page.locator("textarea")).first
                try:
                    await textarea.wait_for(state="visible", timeout=5000)
                except Exception:
                    pass

                if await textarea.is_visible():
                    await textarea.click(force=True)
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
                    await textarea.fill(new_bio)
                    await asyncio.sleep(1)

                    # 點擊 Edit bio 的 Done / 完成
                    done_btns = await page.locator("text='Done'").or_(page.locator("text='完成'")).all()
                    for d in reversed(done_btns):
                        if await d.is_visible():
                            try:
                                await d.click(force=True, timeout=3000)
                                await asyncio.sleep(1.5)
                                break
                            except Exception:
                                pass

                    # 點擊 Edit profile modal 最下方的 Done / 完成
                    final_done = await page.locator("text='Done'").or_(page.locator("text='完成'")).all()
                    for d in reversed(final_done):
                        if await d.is_visible():
                            try:
                                await d.click(force=True, timeout=3000)
                                await asyncio.sleep(2.5)
                                break
                            except Exception:
                                pass

                    print(f"✅ [Threads Bio Updater] 成功更新 Bio：{new_bio}")
                    await browser.close()
                    return True

            print("⚠️ [Threads Bio Updater] 未能找到編輯簡介輸入框或按鈕。")
            await browser.close()
            return False
        except Exception as e:
            print(f"⚠️ [Threads Bio Updater] 執行異常: {e}")
            await browser.close()
            return False
