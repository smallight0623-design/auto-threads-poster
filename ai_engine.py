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

def select_best_post_material(candidates: list, strategy_prompt: str, game_name: str, config: dict, campaign_status: dict = None) -> dict:
    """
    AI 智慧爆款選品器 (Material Curator):
    從多個平台（Reddit、X、巴哈姆特、Twitch 等）收集的候選爆文中，依據該帳號的營運使命（獲取最多粉絲與關注度），
    結合當前作戰戰役階段（常規巡航 vs 預熱期 vs 首發引爆日 vs 餘波開荒期），
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

    # 戰役階段動態提示詞注入
    campaign_directive = ""
    if campaign_status and campaign_status.get("phase") in ["WARMUP", "LAUNCH_DAY", "AFTERMATH"]:
        m = campaign_status.get("milestone", {})
        phase = campaign_status.get("phase")
        m_title = m.get("title", "")
        if phase == "WARMUP":
            days = campaign_status.get("days_diff", 0)
            campaign_directive = f"""
【🚨 當前特殊作戰戰役 - 預熱宣傳期（倒數 {days} 天）】：
目前社群正處於重大事件【{m_title}】的倒數衝刺期！粉絲與玩家對此事件高度飢渴。
如果候選貼文中存在任何與【{m_title}】直接相關的前瞻爆料、測試情報、實機畫面、倒數預熱或規格討論，請【極度高度加權優先入選】！並在選材決策理由中明確指出此篇符合預熱戰役目標。
"""
        elif phase == "LAUNCH_DAY":
            campaign_directive = f"""
【🚨 當前特殊作戰戰役 - 正式引爆日（年度巔峰）】：
今日為重大事件【{m_title}】的正式上線/引爆日！全網流量最高峰！
請極度優先挑選第一時間的實機體驗、首發試玩、捏臉/初見神操作或震撼反響貼文！
"""
        elif phase == "AFTERMATH":
            days = campaign_status.get("days_since", 1)
            campaign_directive = f"""
【📈 當前特殊作戰戰役 - 餘波開荒攻略期（上線第 {days} 天）】：
目前為【{m_title}】正式上線第 {days} 天！玩家進入開荒深水區，請優先挑選逃課配裝攻略、新手避坑指南、神級彩蛋或好笑翻車！
"""

    # 候選清單概況
    candidates_brief = []
    for idx, c in enumerate(candidates):
        brief = (
            f"【候選 {idx}】(ID: {c['id']})\n"
            f"- 來源平台: {c.get('source_platform', '未知')}\n"
            f"- 互動讚數/觀看: {c.get('upvotes', 0)}\n"
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
{campaign_directive}
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

def detect_future_events(raw_posts: list, game_name: str, config: dict) -> list:
    """
    一葉知秋：AI 自動嗅探未來重大事件時間線索
    掃描候選貼文中是否出現發售日、測試、發表會、DLC 等未來的具體時間點。
    若發現具體情報，提取結構化事件並回傳。
    """
    keywords = ["release date", "launch date", "coming on", "scheduled on", "trailer on", "beta starts", "預計於", "將於", "發售日", "上線"]
    suspicious_posts = []
    for p in raw_posts:
        text = f"{p.get('title', '')} {p.get('full_content', '')}".lower()
        if any(k in text for k in keywords):
            suspicious_posts.append(p)

    if not suspicious_posts:
        return []

    base_url = (os.getenv("AI_BASE_URL") or config.get("AI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    api_key = os.getenv("AI_API_KEY") or config.get("AI_API_KEY", "")
    primary_model = config.get("AI_MODEL", "gemini-2.5-flash")

    snippets = []
    for p in suspicious_posts[:5]:
        snippets.append(f"標題: {p.get('title', '')}\n內文: {p.get('full_content', '')[:150]}")
    
    combined = "\n---\n".join(snippets)

    prompt = f"""
你是一位情報分析師。請分析以下社群貼文中，是否提到了關於【{game_name}】未來預計發生的「具體重大事件」（如：發售日、測試日、發表會、DLC上線日）：
{combined}

【要求】：
如果存在具體日期（如 2026 年幾月幾號），請提取並以 JSON 陣列格式回傳：
[
  {{
    "title": "事件簡稱 (例如：遊戲正式發售 / 公開測試)",
    "target_date": "YYYY-MM-DD",
    "keywords": ["關鍵字1", "關鍵字2"],
    "source_title": "來源貼文標題"
  }}
]
若無具體明確之未來日期，請單純回傳空陣列 []。不要有任何 Markdown 或多餘引言。
"""
    try:
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        res = requests.post(url, headers=headers, json={
            "model": primary_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }, timeout=15)
        if res.status_code == 200:
            import json, re
            c = res.json()["choices"][0]["message"]["content"]
            match = re.search(r"\[.*\]", c, re.DOTALL)
            if match:
                return json.loads(match.group(0))
    except Exception as e:
        print(f"[Event Discovery] 嗅探異常: {e}")
    return []

def generate_human_persona_bio(game_name: str, persona: dict, campaign_status: dict, config: dict) -> str:
    """
    真人化生活感 Bio 生成器：
    徹底擺脫「搬運工/情報站/行銷號」的冰冷口吻，
    以「熱愛該遊戲、有生活感、有情緒、偶爾自嘲」的真實玩家同行者視角，
    並將當前戰役大作的倒數節奏（例如已請好假等測試）自然融入自我介紹中。
    """
    base_url = (os.getenv("AI_BASE_URL") or config.get("AI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    api_key = os.getenv("AI_API_KEY") or config.get("AI_API_KEY", "")
    primary_model = config.get("AI_MODEL", "gemini-2.5-flash")

    identity = persona.get("identity", "每天上班摸魚的狂熱玩家")
    tone_style = persona.get("tone_style", "幽默、自嘲、熱血、愛用玩家社群黑話與生活感")
    catchphrase = persona.get("catchphrase", "假單已經送出去了")

    # 戰役情境注入
    camp_ctx = "目前處於日常狩獵與排位常態，持續抓全網最好笑與最頂高光。"
    if campaign_status and campaign_status.get("phase") != "CRUISE":
        m = campaign_status.get("milestone", {})
        m_title = m.get("title", "")
        phase = campaign_status.get("phase")
        if phase == "WARMUP":
            days = campaign_status.get("days_diff", 0)
            camp_ctx = f"距離重大事件【{m_title}】倒數僅剩 {days} 天！你處於極度興奮狀態（例如已經跟老闆請好假、準備熬夜開荒、每天都在算日子）。"
        elif phase == "LAUNCH_DAY":
            camp_ctx = f"今日是重大事件【{m_title}】的正式發售/解鎖引爆日！今晚不用睡了，正全速開荒中。"
        elif phase == "AFTERMATH":
            days = campaign_status.get("days_since", 1)
            camp_ctx = f"【{m_title}】剛上線第 {days} 天，深陷開荒深水區，正在測試各種逃課流派與避坑。"

    prompt = f"""
你是一位身價百萬的頂級社群人設架構師。請為一位在 Threads/Facebook 上的【{game_name}】狂熱玩家撰寫一段簡短、極度有靈魂且「完全像真人」的個人簡介（Bio）。

【玩家真人人設設定】：
- 核心身分：{identity}
- 說話口氣風格：{tone_style}
- 個人特色口癖/常掛嘴邊的話：{catchphrase}
- 當前生活情境與大作戰役：{camp_ctx}

【極致要求（不可違背）】：
1. 必須 100% 像活生生的人類玩家，散發真誠熱愛、自嘲與生活感（例如：上班摸魚、假單已送、被隊友氣到中風、手殘貓車）。
2. 嚴格禁止出現任何機器人、行銷號或搬運工辭藻（嚴禁出現：情報站、彙整、轉載、搬運、機器人、最新資訊、分享好康、基地的字眼）。
3. 保持簡潔有力（長度約 45 ~ 85 個字，2~3 句以內），自然點綴 2~3 個 Emoji。
4. 直接輸出最終 Bio 文案，絕不要任何額外解釋或 Markdown 引號。
"""
    try:
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        res = requests.post(url, headers=headers, json={
            "model": primary_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }, timeout=15)
        if res.status_code == 200:
            c = res.json()["choices"][0]["message"]["content"].strip()
            # 清理可能的開場白前言 (例如「以下是...」或「出爐：」)
            lines = [l.strip() for l in c.split("\n") if l.strip()]
            if len(lines) > 1 and any(k in lines[0] for k in ["出爐", "以下是", "打造", "為你", "Bio：", "簡介："]):
                c = "\n".join(lines[1:]).strip()
            # 清理可能的引號
            c = c.strip('"').strip("'").strip("「").strip("」").strip()
            return c
    except Exception as e:
        print(f"[Persona Bio] 生成失敗: {e}")
    
    return f"🎮 {identity} ｜ 專抓全網最頂高光與極限翻車 ｜ 獵友隨時來聊 🍺"

def run_weekly_reflection(acc_id: str, posts_history: list, current_strategy: str, persona: dict, campaign_status: dict, config: dict) -> dict:
    """
    AI 每週營運覆盤與防過度擬合演算法 (Anti-Overfitting Weekly Reflection Engine)：
    1. 統計歷史貼文成效，評估各形式（短影音 vs 圖片 vs 文字）之勝率
    2. 導入 Epsilon-Greedy (80/20 探索與利用)：80% 保留成熟題材 + 20% 強制探索未知創新
    3. 過濾倖存者偏差與防同質化審美疲勞
    4. 輸出覆盤反思報告、微調後的 strategy_prompt、以及最新戰役 Bio
    """
    base_url = (os.getenv("AI_BASE_URL") or config.get("AI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    api_key = os.getenv("AI_API_KEY") or config.get("AI_API_KEY", "")
    primary_model = config.get("AI_MODEL", "gemini-2.5-flash")
    game_name = config.get("GAME_NAME", "遊戲")

    # 1. 數據統計概況
    total_samples = len(posts_history)
    video_posts = [p for p in posts_history if p.get("media_type") == "VIDEO"]
    image_posts = [p for p in posts_history if p.get("media_type") == "IMAGE"]
    text_posts = [p for p in posts_history if p.get("media_type") == "TEXT"]

    def avg_upvotes(sublist):
        if not sublist:
            return 0
        return round(sum(p.get("upvotes", 0) for p in sublist) / len(sublist), 1)

    sorted_posts = sorted(posts_history, key=lambda x: x.get("upvotes", 0), reverse=True)
    top_3 = sorted_posts[:3]
    bottom_3 = sorted_posts[-3:] if len(sorted_posts) >= 3 else []

    top_str = "\n".join([f"- [{p.get('source_platform')}] {p.get('title', '')[:40]}... (👍 {p.get('upvotes')} 讚, 形式: {p.get('media_type')})" for p in top_3])
    bottom_str = "\n".join([f"- [{p.get('source_platform')}] {p.get('title', '')[:40]}... (👍 {p.get('upvotes')} 讚, 形式: {p.get('media_type')})" for p in bottom_3])

    camp_str = campaign_status.get("badge_text", "常規巡航") if campaign_status else "常規巡航"

    prompt = f"""
你是一位兼具「量化對沖基金研究員思維」與「社群流量操盤手」的頂級 AI 策略總監。
請針對社群帳號【{game_name}】進行深入的【每週營運覆盤與防過度擬合反思 (Weekly Reflection)】。

【歷史數據摘要】：
- 總樣本貼文數：{total_samples} 篇
- 短影音 (VIDEO)：{len(video_posts)} 篇，平均互動：{avg_upvotes(video_posts)}
- 圖文 (IMAGE)：{len(image_posts)} 篇，平均互動：{avg_upvotes(image_posts)}
- 純文字 (TEXT)：{len(text_posts)} 篇，平均互動：{avg_upvotes(text_posts)}
- 當前戰役階段：{camp_str}
- 當前營運策略：{current_strategy}

【成效最頂尖前 3 篇】：
{top_str or '無'}

【成效較平淡後 3 篇】：
{bottom_str or '無'}

【核心反思準則（嚴格執行防過度擬合）】：
1. 【杜絕單一指標過度擬合】：絕不能因為某張搞笑梗圖拿到高讚，就得出「以後全部只發迷因」的幼稚結論。擴散型資產（梗圖/短影音）負責拉新，權威型資產（深度配裝/官方機制解析）負責建立忠誠度與留存，兩者不可偏廢。
2. 【80/20 探索與利用 (Epsilon-Greedy)】：
   - 80% 利用（Exploitation）：保留歷史驗證勝率最高的話題（如短影音翻車高光、核心前瞻情報）。
   - 20% 強制探索（Exploration）：明確規劃 20% 的試驗配額，去測試冷門新領域、小眾玩法討論或深度故事彩蛋，防止受眾審美疲勞。
3. 【倖存者偏差過濾】：分析高讚貼文是否屬於不可複製的偶發事件。
4. 【微調策略提示詞】：在保持帳號核心護城河的前提下，給出微調後的全新 `tuned_strategy`。

【輸出規範】：
必須且僅能以 JSON 格式回傳，格式如下：
{{
  "insight_summary": "150字左右的本週發布數據洞察與成效對比分析",
  "anti_overfitting_notes": "150字左右的防過度擬合分析，明確點出 80% 核心基石與 20% 探索試驗方向",
  "tuned_strategy": "微調後的帳號營運策略提示詞（約 60~100 字，供下週選材使用）"
}}
"""
    try:
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        res = requests.post(url, headers=headers, json={
            "model": primary_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        }, timeout=25)
        if res.status_code == 200:
            import json, re
            c = res.json()["choices"][0]["message"]["content"]
            match = re.search(r"\{.*\}", c, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                # 順便生成配合當前戰役的最新 Bio
                data["recommended_bio"] = generate_human_persona_bio(game_name, persona, campaign_status, config)
                return data
    except Exception as e:
        print(f"[Weekly Reflection] 覆盤執行異常: {e}")

    # Fallback
    fallback_bio = generate_human_persona_bio(game_name, persona, campaign_status, config)
    return {
        "insight_summary": f"本週累計分析 {total_samples} 篇貼文數據。短影音與熱門圖文互動表現良好，受眾對即時情報敏感度高。",
        "anti_overfitting_notes": "實施 80/20 探索利用策略：80% 鎖定高讚短片與核心前瞻，保留 20% 份額探索冷門配裝與玩家討論，防止審美疲勞。",
        "tuned_strategy": current_strategy or "優先挑選最有料、最好笑、最具社群傳播力的即時爆文，並保留20%探索冷門硬核機制。",
        "recommended_bio": fallback_bio
    }
