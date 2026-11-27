import os
import sys
import json
import random
import requests
import datetime
from typing import Dict, Any, List, Optional

import account_manager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==============================================================================
# 🧠 模組一：意圖識別與客戶資格審查器 (Intent Qualification Filter)
# 架構借鑑：kaymen99/sales-outreach-automation-langgraph
# ==============================================================================

def evaluate_lead_intent(post_text: str, game_name: str, config: dict) -> dict:
    """
    對目標社群貼文進行深度意圖分析 (打分 1~5 分)：
    - 5分：極高意圖（明確尋求建議、卡關求救、尋找隊友、問裝備怎麼配）
    - 4分：高意圖（抱怨野團坐牢、抱怨自己打不過、新手剛入坑迷茫）
    - 3分：泛泛討論／心得分享（無推銷切入點）
    - 1~2分：純發洩抱怨、辱罵遊戲、官方新聞、純無意義曬圖（直接跳過）
    """
    base_url = (os.getenv("AI_BASE_URL") or config.get("AI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    api_key = os.getenv("AI_API_KEY") or config.get("AI_API_KEY", "")
    primary_model = config.get("AI_MODEL", "gemini-2.5-flash")

    prompt = f"""
你是一位深諳社群心理學的「AI 客戶意圖分析專家」。
請分析以下這篇在 Threads 上的【{game_name}】玩家貼文：

\"\"\"{post_text}\"\"\"

【任務評估指標】：
1. **第一道絕對關卡**：這篇貼文**是否真的是在討論【{game_name}】（魔物獵人系列）**？如果它是在講《荒野亂鬥 / Brawl Stars》、《荒野行動》、《RuneScape Dragonwilds》、《薩爾達曠野之息》或其他遊戲／日常無關話題，必須直接判定 `is_target_game: false`、`intent_score: 1`、`should_reply: false`！
2. 該玩家是否具有「求助、卡關、找隊友、需要配裝攻略、或對當前現狀感到痛苦」的明確痛點？
3. 我們是否有切入給予「解答 ＋ 推薦高品質獵人連線群/同伴」的自然空間？

【打分維度 (1 ~ 5 分)】：
- 5分：明確在聊【{game_name}】且強烈求助或徵隊友（例如「歷戰王到底怎麼打？」、「有人能一起連線嗎？」、「剛入坑推薦玩什麼？」）
- 4分：明確在聊【{game_name}】且有強烈痛點但偏向吐槽（例如「野團又三貓心好累」、「單刷一直超時到底差在哪」、「身邊都沒朋友玩」）
- 3分：普通【{game_name}】遊戲日常（例如「今天終於做完這套了」、「這隻魔物長得好魔性」）
- 1~2分：非目標遊戲（如荒野亂鬥等）、純謾罵、政治、官方更新轉發、無實質內容

【回傳格式要求（必須且僅能以 JSON 回傳）】：
{{
  "is_target_game": true或false,
  "intent_score": 1到5的整數,
  "intent_category": "SEEKING_ADVICE | LOOKING_FOR_GROUP | GAMEPLAY_STRUGGLE | CASUAL_CHAT | IRRELEVANT",
  "pain_point": "原PO的核心痛點或困擾（15字以內，若無則填無）",
  "should_reply": true若(is_target_game為true且score>=4)否則false,
  "reason": "簡述判定理由 (20字以內)"
}}
"""
    import time
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    for attempt in range(2):
        try:
            res = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={
                    "model": primary_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                },
                timeout=25
            )
            if res.status_code == 200:
                c = res.json()["choices"][0]["message"]["content"]
                import re
                m = re.search(r"\{.*\}", c, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
                    if parsed.get("is_target_game") is False:
                        parsed["intent_score"] = 1
                        parsed["should_reply"] = False
                    return parsed
        except Exception as e:
            print(f"⚠️ [Intent Evaluator] 第 {attempt+1} 次意圖評估異常: {e}")
            if attempt == 0:
                time.sleep(2)

    # Fallback default: do NOT force reply when API fails
    return {
        "is_target_game": False,
        "intent_score": 1,
        "intent_category": "IRRELEVANT",
        "pain_point": "無",
        "should_reply": False,
        "reason": "評估連線失敗安全跳過"
    }

# ==============================================================================
# 🥷 模組二：變色龍隱形推銷生成器 (Chameleon Stealth Generator)
# 架構借鑑：AICMO/AiCMO-Marketing-Prompt-Collection
# 採用黃金 80/20 刺客原則：80% 專業硬核解法 ＋ 20% 第三方無辜分享
# ==============================================================================

def generate_stealth_chameleon_reply(
    post_text: str,
    author: str,
    pain_point: str,
    game_name: str,
    config: dict,
    product_context: dict = None
) -> str:
    """
    生成高情商、高專業度、零廣告感的變色龍回覆：
    - 前 80%：針對對方具體痛點，給出真正有用、扎實的實戰建議（建立絕對專家信任）。
    - 後 20%：以「我也是受害者，後來找到好解法」的第三方視角自然帶出（如 Discord 語音連線群）。
    - 嚴格禁止所有行銷號詞彙，不放生硬外部連結，讓人主動想看個人主頁！
    """
    base_url = (os.getenv("AI_BASE_URL") or config.get("AI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    api_key = os.getenv("AI_API_KEY") or config.get("AI_API_KEY", "")
    primary_model = config.get("AI_MODEL", "gemini-2.5-flash")

    if not product_context:
        product_context = {
            "name": "魔物獵人荒野開荒 Discord 群",
            "benefit": "每天晚上都有滿編語音房、老獵人連線帶飛、不坐牢、分享配裝與捏臉數據",
            "access_method": "個人主頁 Bio 有專屬進群連結"
        }

    prod_name = product_context.get("name", "獵人交流群")
    prod_benefit = product_context.get("benefit", "語音連線、老手帶打、不用在野團坐牢")

    prompt = f"""
你是一位身在台灣 Threads 的頂級【{game_name}】老手玩家。
你看見了玩家 @{author} 發布的這篇貼文：
\"\"\"{post_text}\"\"\"

【已偵測核心痛點】：{pain_point}
【我們的軟性推廣標的】：{prod_name}（亮點：{prod_benefit}）

【AICMO 變色龍隱形推銷四大鐵律（嚴格執行）】：
1. 【80% 扎實專業解答（建立絕對信任）】：
   - 開頭先針對他貼文提到的魔物、武器、配裝或卡關點，給予 1~2 個具體、切題且實用的老手建議（證明你是同好高手）。
   - 如果原文根本只是閒聊或不是在問攻略，請自然聊天就好，不要硬塞無關的「集中模式／防禦裝」公式！
2. 【20% 見縫插針（自然多變，拒絕複製貼上感）】：
   - 絕不能像客服或行銷號，也**不要每篇都重複「野團血壓飆高 / 滿編房 / 捏臉數據」同一套話術**！
   - 僅在原PO真的遇到孤單單刷、打不過、或想找人時，才輕描淡寫帶一句自己的解決辦法（例如「後來我都跟 DC 語音認識的幾個獵友固定晚上開一兩場，有人報招真的差很多」或「配裝直接找 DC 群裡的大佬問比較快少走彎路」）。如果話題不適合提到 DC 群，就純粹給實用建議交朋友即可！
3. 【紅線禁詞庫（違者死罪）】：
   - 嚴禁出現：「歡迎加入」、「推薦大家」、「點我主頁」、「官方」、「專屬優惠」、「點此連結」。
   - 嚴禁放任何 raw URL 網址（Threads 上放連結會直接被降權判定為垃圾訊息）。
4. 【語氣與長度】：
   - 台灣道地玩家口吻，口語自然、不說教、無機器人腔。
   - 總長度嚴格控制在 45 ~ 105 個字以內！精簡有力。

【輸出要求】：直接輸出最終回覆內容，不要任何多餘引號或前言。
"""
    import time
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    for attempt in range(2):
        try:
            res = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={
                    "model": primary_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.65
                },
                timeout=25
            )
            if res.status_code == 200:
                c = res.json()["choices"][0]["message"]["content"].strip()
                c = c.strip('"').strip("'").strip("「").strip("」").strip()
                if c:
                    return c
        except Exception as e:
            print(f"⚠️ [Chameleon Reply] 第 {attempt+1} 次生成失敗: {e}")
            if attempt == 0:
                time.sleep(2)

    return ""

# ==============================================================================
# 📊 模組三：推銷潛在客戶追蹤器 (Lead Tracker)
# ==============================================================================

def get_leads_file(acc_id: str) -> str:
    acc_dir = os.path.join(BASE_DIR, "accounts", acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    return os.path.join(acc_dir, "sales_leads.json")

def log_sales_lead(acc_id: str, lead_data: dict):
    fpath = get_leads_file(acc_id)
    leads = []
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                leads = json.load(f)
        except Exception:
            pass
    lead_data["id"] = f"lead_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(100, 999)}"
    lead_data["created_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    leads.append(lead_data)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)
    print(f"📌 [Sales Lead] 已登記潛在客戶追蹤：@{lead_data.get('author')} (Intent: {lead_data.get('intent_score')}分)")
