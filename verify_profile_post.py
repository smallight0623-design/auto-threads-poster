import asyncio
import os
import sys
from playwright.async_api import async_playwright

session_file = r"C:\Users\d4414\.gemini\antigravity\scratch\auto_threads_poster\accounts\acc_primary\session.json"
proof_path = r"C:\Users\d4414\.gemini\antigravity\brain\b07effa5-8267-4988-9eec-6f8f631667d6\threads_live_published_profile.png"

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=session_file,
            viewport={"width": 1280, "height": 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        print("直接導向個人主頁 https://www.threads.net/@dinosaur.56467484 ...")
        await page.goto("https://www.threads.net/@dinosaur.56467484", wait_until="domcontentloaded")
        await asyncio.sleep(5)
        
        await page.screenshot(path=proof_path)
        print(f"Profile screenshot saved: {proof_path}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(check())
