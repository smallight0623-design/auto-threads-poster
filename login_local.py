import asyncio
import os
import sys
import subprocess
from playwright.async_api import async_playwright

# 強制 Windows 終端機使用 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SESSION_FILE = "threads_session.json"

async def main():
    print("=" * 65)
    print(" 🚀【Threads 矩陣社群帳號 — 一鍵 Session Cookie 登入工具】")
    print("=" * 65)
    print("即將為您彈出 Chrome 瀏覽器視窗，請在視窗內登入您的 Threads 帳號。")
    print("（若有發送 SMS 簡訊驗證碼或兩步驟驗證，請正常在瀏覽器內輸入）\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--start-maximized"]
        )
        context = await browser.new_context(no_viewport=True)
        page = await context.new_page()

        print("[步驟 1/3] 正在開啟 Threads 登入頁面...")
        await page.goto("https://www.threads.net/login")

        print("[步驟 2/3] 請在彈出的瀏覽器中登入 Threads。")
        input("\n👉 看到 Threads 動態首頁、確認登入完成後，請在此視窗按下【Enter】鍵：")

        print("\n[步驟 3/3] 正在擷取 Session 與 Cookie...")
        await context.storage_state(path=SESSION_FILE)
        
        # 讀取剛剛產生的 session 內容
        session_text = ""
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                session_text = f.read()
        except Exception as e:
            print(f"讀取 Session 失敗: {e}")

        # 自動複製至 Windows 剪貼簿 (便利性升級)
        copied_to_clipboard = False
        if session_text:
            try:
                p_clip = subprocess.Popen(['clip.exe'], stdin=subprocess.PIPE, shell=True)
                p_clip.communicate(input=session_text.encode('utf-16le'))
                copied_to_clipboard = True
            except Exception:
                try:
                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value (Get-Content -Raw -Encoding utf8 threads_session.json)"],
                        check=False
                    )
                    copied_to_clipboard = True
                except Exception:
                    pass

        print("\n" + "=" * 65)
        print(" 🎉 登入成功！Session 已成功擷取！")
        if copied_to_clipboard:
            print(" 📋【超方便】：Session 內容已自動複製到您的剪貼簿！")
            print("    👉 您現在只需打開主控台 (http://127.0.0.1:8000)")
            print("    👉 點擊「➕ 新增社群帳號工作台」，在 Cookie 欄位按 Ctrl + V 貼上即可！")
        else:
            print(f" 檔案已儲存至：{os.path.abspath(SESSION_FILE)}")
            print(" 請將該檔案內容複製並貼入主控台。")
        print("=" * 65 + "\n")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
