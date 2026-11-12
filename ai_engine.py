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
    custom_tags = config.get("CUSTOM_TAGS", "").strip()

    # 候選模型重試清單
    candidate_models = [primary_model]
    for fallback in ["gemini-2.5-flash", "gemini-3.8-flash", "gpt-4o-mini", "gemini-2.0-flash"]:
        if fallback not in candidate_models:
            candidate_models.append(fallback)

    if custom_tags:
        hashtag_instruction = f"""4. 【主題標籤（Hashtags）】：
   - Threads 與 FB 演算法極度看重主題標籤！請在文案最末尾另起一行，務必附上以下指定的主題標籤：
     {custom_tags}"""
    else:
        hashtag_instruction = f"""4. 【演算法爆款主題標籤（Hashtags）】：
   - Threads 與 FB 演算法極度看重主題標籤！請在文案最末尾另起一行，依據【{game_name}】與【{target_region}】，自動精準附上 2~3 個該遊戲在該地區最熱門的搜尋主題標籤（例如：#魔物獵人旅人 #魔物獵人 等），最大化擴散觸及率。"""

    system_prompt = f"""
你是一位全球頂級的跨國社群與遊戲在地化翻譯專家。
【任務目標】：將國外社群的原貼文 100% 忠實翻譯至目標地區的語言，進行跨平台熱文無痕呈現。

【關鍵參數】：
- 目標遊戲/主題：{game_name}
- 目標地區/語言：{target_region}

【核心翻譯守則（嚴格執行）】：
1. 【完全照抄，零增刪改動】：
   - 保持 1:1 的結構對齊，包括原文所有的段落換行、Emoji 表情符號、標點符號、大小寫語氣。
   - 嚴格保留原作者的所有情緒、語氣與語感（例如憤怒、吐槽、激動、諷刺或冷靜）。
   - 嚴禁擅自改寫、總結、修飾或添加任何原作者沒說的話（例如「筆者認為」、「大家好」、「這是一篇搬運」等客套廢話一律不准出現）。

2. 【嚴格不標作者與來源】：
   - 嚴禁標註原作者 ID、帳號名稱、或來源網站（例如嚴禁出現「作者：xxx」、「轉自 Reddit/Threads」、「Source:」等文字）。
   - 純粹以 1:1 匿名社群分享內容直接呈現。

3. 【地區語言與專有名詞極致對齊】：
   - 譯文必須符合【{target_region}】當地玩家日常最自然的母語表達習慣（例如目標為台灣時，必須使用台灣道地繁體中文，嚴禁大陸用語；目標為越南時，使用自然越南語）。
   - 文中涉及【{game_name}】的所有專有名詞（包括角色名、技能、道具、裝備、遊戲機制、官方公告術語、社群通用黑話），必須精確替換為該遊戲在【{target_region}】官方伺服器/官方在地化版本的標準譯名。

{hashtag_instruction}

5. 【輸出規格】：
   - 直接輸出最終翻譯完成的純文案內容（含末尾標籤），不要有任何多餘的引言、前綴或解釋。
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

def select_best_post_material(candidates: list, strategy_prompt: str, game_name: str, config: dict) -> dict:
    """
    AI 智慧爆款選品器 (Material Curator):
    從多個平台（Reddit、X、巴哈姆特等）收集的候選爆文中，依據該帳號的營運使命（獲取最多粉絲與關注度），
    客觀挑選出最有料、最好笑、最吸睛或最具流量爆發潛力的單一候選貼文。
    注意：僅做選材決策，絕不篡改候選貼文本身的素材、圖片、影片或原文內容！
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    base_url = (os.getenv("AI_BASE_URL") or config.get("AI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    api_key = os.getenv("AI_API_KEY") or config.get("AI_API_KEY", "")
    primary_model = config.get("AI_MODEL", "gemini-2.5-flash")

    # 候選清單概況
    candidates_brief = []
    for idx, c in enumerate(candidates):
        brief = (
            f"【候選 {idx}】(ID: {c['id']})\n"
            f"- 來源平台: {c.get('source_platform', '未知')}\n"
            f"- 互動讚數: {c.get('upvotes', 0)}\n"
            f"- 媒體類型: {c.get('media_type', 'TEXT')}\n"
            f"- 標題/主旨: {c.get('title', '')[:80]}\n"
            f"- 內容片段: {c.get('full_content', '')[:200]}..."
        )
        candidates_brief.append(brief)
    
    briefs_text = "\n\n".join(candidates_brief)

    curator_prompt = f"""
你是一位身價百萬的頂級社群營運操盤手與流量總監。
【帳號核心終極目標】：在【{game_name}】領域中取得最多的粉絲、讚數與社群關注度。
【該帳號專屬營運策略】：{strategy_prompt or '優先挑選最有料、最好笑、最具傳播力、最有共鳴感的爆款內容'}

以下是從各平台即時掃描收集到的 {len(candidates)} 篇候選爆文：
{briefs_text}

【評選任務】：
請綜合分析這幾篇貼文的「話題性、爆笑程度、吸睛度、圖片/影片傳播力、粉絲互動意願」，從中選出最符合上述策略、最容易在社群爆發的唯一【最佳候選】。

【回傳格式要求】：
你必須且僅能以 JSON 格式回傳，格式如下：
{{
  "selected_index": 0,
  "reason": "挑選理由簡述（例如：這張迷因圖非常切合近期遊戲痛點，笑點強烈且互動讚數飆升快）"
}}
"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        url = f"{base_url}/chat/completions"
        payload = {
            "model": primary_model,
            "messages": [
                {"role": "user", "content": curator_prompt.strip()}
            ],
            "temperature": 0.3
        }
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        if res.status_code == 200:
            content = res.json()["choices"][0]["message"]["content"]
            import json, re
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                idx = int(parsed.get("selected_index", 0))
                reason = parsed.get("reason", "AI 評選為最佳爆款素材")
                if 0 <= idx < len(candidates):
                    chosen = candidates[idx]
                    chosen["curation_reason"] = reason
                    print(f"🎯 [AI 選材決策] 選中候選 {idx} ({chosen['id']})：{reason}")
                    return chosen
    except Exception as e:
        print(f"⚠️ [AI 選材評估] 呼叫逾時或異常 ({e})，自動採用讚數最高之候選貼文")

    candidates.sort(key=lambda x: x.get("upvotes", 0), reverse=True)
    return candidates[0]
