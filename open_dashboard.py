import sys
import time
import urllib.request
import webbrowser
import subprocess
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PORT = 8000
URL = f"http://127.0.0.1:{PORT}"

def is_running():
    try:
        with urllib.request.urlopen(f"{URL}/api/data", timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False

def main():
    print("=" * 60)
    print(" 🚀【Threads 矩陣社群發文系統 — 智慧主控台啟動器】")
    print("=" * 60)

    if is_running():
        print(f"\n✅ 主控台服務已在運行中！(連接埠 {PORT})")
        print(f"👉 正在為您開啟主控台頁面：{URL}")
        webbrowser.open(URL)
    else:
        print(f"\n⏳ 正在為您啟動主控台後端服務 (連接埠 {PORT})...")
        proj_dir = os.path.dirname(os.path.abspath(__file__))
        dashboard_script = os.path.join(proj_dir, "dashboard.py")
        
        # 在獨立背景行程啟動 dashboard
        subprocess.Popen(
            [sys.executable, dashboard_script],
            cwd=proj_dir,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )

        # 等待服務就緒
        ready = False
        for _ in range(15):
            time.sleep(0.5)
            if is_running():
                ready = True
                break

        if ready:
            print("🎉 主控台服務啟動成功！")
            print(f"👉 正在為您開啟主控台頁面：{URL}")
            webbrowser.open(URL)
        else:
            print("⚠️ 啟動時間稍長，請直接在瀏覽器開啟：", URL)
            webbrowser.open(URL)

    print("\n" + "=" * 60)
    print(" 視窗將在 3 秒後自動關閉，祝您使用愉快！")
    print("=" * 60)
    time.sleep(3)

if __name__ == "__main__":
    main()
