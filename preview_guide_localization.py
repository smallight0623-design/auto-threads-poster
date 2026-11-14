import os
import sys
import json

sys.path.insert(0, r"C:\Users\d4414\.gemini\antigravity\scratch\auto_threads_poster")
import account_manager
import ai_engine

report_file = r"C:\Users\d4414\.gemini\antigravity\scratch\auto_threads_poster\lighthouse_test_report.json"
with open(report_file, "r", encoding="utf-8") as f:
    report = json.load(f)

winner = report.get("selected_winner")
raw_content = winner.get("full_content", "")

global_settings = account_manager.get_global_settings()
ai_config = {
    "AI_BASE_URL": global_settings.get("AI_BASE_URL"),
    "AI_API_KEY": global_settings.get("AI_API_KEY"),
    "AI_MODEL": global_settings.get("AI_MODEL") or "gemini-2.5-flash",
    "TARGET_REGION": "台灣 (繁體中文)",
    "GAME_NAME": "Monster Hunter Wilds",
    "CUSTOM_TAGS": "#魔物獵人荒野 #魔物獵人 #重弩配裝"
}

text = ai_engine.call_ai_proxy(raw_content, ai_config)
print("=== Final Card Output ===")
print(text)
print("==========================")
print("Length:", len(text))
