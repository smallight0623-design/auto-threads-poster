import os
import sys
import json
import requests

sys.path.insert(0, r"C:\Users\d4414\.gemini\antigravity\scratch\auto_threads_poster")
import account_manager

report_file = r"C:\Users\d4414\.gemini\antigravity\scratch\auto_threads_poster\lighthouse_test_report.json"
with open(report_file, "r", encoding="utf-8") as f:
    report = json.load(f)

winner = report.get("selected_winner")
raw_content = winner.get("full_content", "")

human_gamer_prompt = """你是一位重度沉迷魔物獵人的台灣老獵人玩家。
【任務】：將這篇重弩攻略精華，以「台灣玩家在 Threads 上分享好用配裝給獵友抄作業」的口吻發文。

【徹底去除 AI 味與說教感守則（極重要）】：
1. 嚴禁寫成冷冰冰的規格說明書、條列填空表或老師說教指南（不要寫「🎯 主力流派：通常彈 ▫️ 武器：xxx ▫️ 核心技能：xxx 💡 關鍵提示：xxx」這種機械模板）！
2. 像個真實的台灣遊戲老鳥：熱情、直爽、愛用社群黑話（例如「兄弟們這套真的香」、「直接把作業端上來給各位抄」、「傷害真的看不懂」、「跟鬼一樣」、「誰用誰知道」）。
3. 將硬核乾貨（護鎖刃/黑蝕弩、黑蝕四件套狂龍+15攻、弱特、抖擻、貫通增傷20%）自然融入熱血或實用的對話式段落中。
4. 全文總長度嚴格控制在 200 ~ 350 字以內，末尾另起一行附上主題標籤。
5. 嚴禁任何 Markdown 星號符號（嚴禁 **粗體** 或 * 星號）！
"""

global_settings = account_manager.get_global_settings()
base_url = (global_settings.get("AI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
api_key = global_settings.get("AI_API_KEY", "")

payload = {
    "model": "gemini-2.5-flash",
    "messages": [
        {"role": "system", "content": human_gamer_prompt},
        {"role": "user", "content": f"【巴哈原文攻略】：\n{raw_content}"}
    ],
    "temperature": 0.3
}

headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
res = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=30)
text = res.json()["choices"][0]["message"]["content"].strip()
print("=== Human Gamer Bro Tone Output ===")
print(text)
print("===================================")
print("Length:", len(text))
