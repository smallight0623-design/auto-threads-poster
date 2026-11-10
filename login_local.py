import asyncio
import os
from playwright.async_api import async_playwright

SESSION_FILE = "threads_session.json"

async def main():
    print("=" * 60)
    print("【Threads 本機一次性 Session 登入導出工具】")
    print("本工具將彈出 Chromium 視窗，請您正常登入 Threads。")
    print("登入成功後，Cookie 與 Session 將自動儲存，供機器人永久免驗證發文使用。")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("\n[1/3] 正在開啟 Threads 登入頁面...")
        await page.goto("https://www.threads.net/login")

        print("[2/3] 請在彈出的瀏覽器中手動完成登入（若有兩步驟驗證請在此輸入）...")
        input("\n👉 看到 Threads 首頁且確認登入完成後，請在此終端機按 [Enter] 鍵繼續：")

        print("\n[3/3] 正在導出 Session Cookie...")
        await context.storage_state(path=SESSION_FILE)
        
        print(f"\n🎉 成功產生 {SESSION_FILE}！")
        print("您可以：")
        print("1. 直接啟動主控台 (python dashboard.py)，將此檔案內容貼入 Cookie 管理區。")
        print("2. 或將檔案內容複製到 GitHub Secrets 的 THREADS_SESSION_DATA 中。")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
