import os
import sys
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def call_ai_proxy(original_text: str, config: dict) -> str:
    """
    通用 AI 中轉站引擎：
    1. 支援所有 OpenAI 相容協議中轉站 (OneAPI, NewAPI, OpenAI, Gemini Proxy 等)
    2. 100% 忠實照抄原文文案（排版、斷行、Emoji、情緒與語氣完全一致，嚴禁加油添醋）
    3. 依據【目標地區】精準切換該地區的道地語言與該遊戲的官方在地化專有名詞
    4. 支援模型容錯自動回退（例如 gemini-2.0-flash 查無管道時自動嘗試 gemini-2.5-flash 或 gpt-4o-mini）
    """
    base_url = (os.getenv("AI_BASE_URL") or config.get("AI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    api_key = os.getenv("AI_API_KEY") or config.get("AI_API_KEY", "")
    target_region = config.get("TARGET_REGION", "台灣 (繁體中文)")
    game_name = config.get("GAME_NAME", "遊戲")
    primary_model = config.get("AI_MODEL", "gemini-2.5-flash")

    # 候選模型重試清單
    candidate_models = [primary_model]
    for fallback in ["gemini-2.5-flash", "gemini-3.8-flash", "gpt-4o-mini", "gemini-2.0-flash"]:
        if fallback not in candidate_models:
            candidate_models.append(fallback)

    system_prompt = f"""
你是一位全球頂級的跨國遊戲在地化翻譯專家。
【任務目標】：將國外遊戲社群的原貼文 100% 忠實翻譯至目標地區的語言。

【關鍵參數】：
- 目標遊戲：{game_name}
- 目標地區/語言：{target_region}

【核心翻譯守則（嚴格執行）】：
1. 【完全照抄，零增刪改動】：
   - 保持 1:1 的結構對齊，包括原文所有的段落換行、Emoji 表情符號、標點符號、大小寫語氣。
   - 嚴格保留原作者的所有情緒、語氣與語感（例如憤怒、吐槽、激動、諷刺或冷靜）。
   - 嚴禁擅自改寫、總結、修飾或添加任何原作者沒說的話（例如「筆者認為」、「大家好」、「這是一篇搬運」等客套廢話一律不准出現）。

2. 【地區語言與專有名詞極致對齊】：
   - 譯文必須符合【{target_region}】當地玩家日常最自然的母語表達習慣（例如目標為台灣時，必須使用台灣道地繁體中文，嚴禁大陸用語；目標為越南時，使用自然越南語）。
   - 文中涉及【{game_name}】的所有專有名詞（包括角色名、技能、道具、裝備、遊戲機制、官方公告術語、社群通用黑話），必須精確替換為該遊戲在【{target_region}】官方伺服器/官方在地化版本的標準譯名。

3. 【輸出規格】：
   - 直接輸出最終翻譯完成的純文案內容，不要有任何多餘的引言或解釋。
"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    last_error = None
    for model in candidate_models:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": f"【待翻譯原文】：\n{original_text}"}
            ],
            "temperature": 0.2
        }

        url = f"{base_url}/chat/completions"
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=60)
        except Exception as e:
            raise Exception(f"AI 中轉站連線逾時或網路錯誤: {str(e)}")

        if res.status_code == 200:
            data = res.json()
            try:
                translated_text = data["choices"][0]["message"]["content"].strip()
                return translated_text
            except (KeyError, IndexError):
                last_error = f"AI 中轉站回應格式異常: {data}"
                continue
        elif "model_not_found" in res.text or res.status_code == 404:
            print(f"中轉站未提供模型 {model}，正在自動切換下一個備援模型重試...")
            last_error = f"模型 {model} 查無管道: {res.text}"
            continue
        else:
            raise Exception(f"AI 中轉站請求失敗 [HTTP {res.status_code}]: {res.text}")

    raise Exception(f"所有候選模型均失敗，最後錯誤: {last_error}")
