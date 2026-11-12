import asyncio
import os
import sys
import subprocess
from playwright.async_api import async_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SESSION_FILE = "facebook_session.json"

async def main():
    print("=" * 65)
    print(" 🚀【Facebook 矩陣社群帳號 — 一鍵 Session Cookie 登入工具】")
    print("=" * 65)
    print("即將為您彈出 Chrome 瀏覽器視窗，請在視窗內登入您的 Facebook 帳號。")
    print("（若有簡訊雙重驗證或通知驗證，請在瀏覽器內正常點擊核准）\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--start-maximized"]
        )
        context = await browser.new_context(no_viewport=True)
        page = await context.new_page()

        print("[步驟 1/3] 正在開啟 Facebook 登入頁面...")
        await page.goto("https://www.facebook.com/")

        print("[步驟 2/3] 請在彈出的瀏覽器中登入 Facebook。")
        input("\n👉 看到 Facebook 動態牆首頁、確認登入完成後，請在此視窗按下【Enter】鍵：")

        print("\n[步驟 3/3] 正在擷取 Session 與 Cookie...")
        await context.storage_state(path=SESSION_FILE)
        
        session_text = ""
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                session_text = f.read()
        except Exception as e:
            print(f"讀取 Session 失敗: {e}")

        # 自動複製至 Windows 剪貼簿
        copied_to_clipboard = False
        if session_text:
            try:
                p_clip = subprocess.Popen(['clip.exe'], stdin=subprocess.PIPE, shell=True)
                p_clip.communicate(input=session_text.encode('utf-16le'))
                copied_to_clipboard = True
            except Exception:
                try:
                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value (Get-Content -Raw -Encoding utf8 facebook_session.json)"],
                        check=False
                    )
                    copied_to_clipboard = True
                except Exception:
                    pass

        print("\n" + "=" * 65)
        print(" 🎉 Facebook 登入成功！Session 已成功擷取！")
        if copied_to_clipboard:
            print(" 📋【超方便】：Facebook Session 已自動複製到您的剪貼簿！")
            print("    👉 您現在只需打開主控台 (http://127.0.0.1:8000)")
            print("    👉 點擊「➕ 新增社群帳號工作台」，發布目標選擇 Facebook，按 Ctrl + V 貼上即可！")
        else:
            print(f" 檔案已儲存至：{os.path.abspath(SESSION_FILE)}")
            print(" 請將該檔案內容複製並貼入主控台。")
        print("=" * 65 + "\n")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
