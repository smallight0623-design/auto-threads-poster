import os
import sys
import json
import uuid
import datetime
import traceback

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_DIR = os.path.join(BASE_DIR, "accounts")
ACCOUNTS_CONFIG_FILE = os.path.join(ACCOUNTS_DIR, "accounts.json")
ANALYTICS_FILE = os.path.join(BASE_DIR, "analytics.json")

def is_fast_track_allowed(acc_id: str) -> bool:
    """檢查該帳號是否具備破裂級爆款插隊資格（必須開啟且已過安全冷卻期）"""
    acc = get_account(acc_id)
    if not acc or not acc.get("enabled", True):
        return False
    if not acc.get("enable_fast_track", True):
        return False
    
    last_run_str = acc.get("last_run", "")
    if not last_run_str:
        return True
    
    try:
        last_dt = datetime.datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S")
        cooldown = int(acc.get("cooldown_minutes") or 45)
        diff_mins = (datetime.datetime.now() - last_dt).total_seconds() / 60
        return diff_mins >= cooldown
    except Exception:
        return True

def log_post_analytics(acc_id: str, entry: dict):
    """記錄發布成效與決策情報至全域與個別帳號數據庫"""
    entry["logged_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry["hour"] = datetime.datetime.now().hour

    acc_dir = os.path.join(ACCOUNTS_DIR, acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    acc_analytics_file = os.path.join(acc_dir, "analytics.json")
    acc_history = []
    if os.path.exists(acc_analytics_file):
        try:
            with open(acc_analytics_file, "r", encoding="utf-8") as f:
                acc_history = json.load(f)
        except Exception:
            pass
    acc_history.append(entry)
    with open(acc_analytics_file, "w", encoding="utf-8") as f:
        json.dump(acc_history, f, indent=2, ensure_ascii=False)

    all_history = []
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE, "r", encoding="utf-8") as f:
                all_history = json.load(f)
        except Exception:
            pass
    all_history.append(entry)
    with open(ANALYTICS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_history, f, indent=2, ensure_ascii=False)

def get_analytics_summary() -> dict:
    """彙總全矩陣營運與發布情報統計"""
    history = []
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass
    
    total_posts = len(history)
    platform_breakdown = {}
    hour_breakdown = {}
    fast_track_count = 0

    for item in history:
        src = item.get("source_platform", "未知")
        platform_breakdown[src] = platform_breakdown.get(src, 0) + 1
        
        hr = item.get("hour", 0)
        hour_breakdown[hr] = hour_breakdown.get(hr, 0) + 1

        if item.get("is_fast_track"):
            fast_track_count += 1

    return {
        "total_posts": total_posts,
        "platform_breakdown": platform_breakdown,
        "hour_breakdown": hour_breakdown,
        "fast_track_count": fast_track_count,
        "recent_logs": history[-20:][::-1]
    }

# ==============================================================================
# 📅 未來重大事件日曆 (Milestone Anticipator) 與戰役生命週期引擎
# ==============================================================================

def get_account_milestones(acc_id: str) -> list:
    """獲取指定帳號的重大事件日曆"""
    acc = get_account(acc_id)
    if not acc:
        return []
    return acc.get("milestones", [])

def save_account_milestones(acc_id: str, milestones: list):
    """持久化重大事件至帳號設定"""
    data = load_data()
    for acc in data.get("accounts", []):
        if acc["id"] == acc_id:
            acc["milestones"] = milestones
            break
    save_data(data)

def add_or_update_milestone(acc_id: str, m_data: dict) -> dict:
    """新增或更新帳號的未來重大事件"""
    milestones = get_account_milestones(acc_id)
    m_id = m_data.get("id")
    if not m_id:
        m_id = f"mile_{uuid.uuid4().hex[:8]}"
        m_data["id"] = m_id
        m_data["created_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        milestones.append(m_data)
    else:
        found = False
        for idx, m in enumerate(milestones):
            if m["id"] == m_id:
                milestones[idx].update(m_data)
                found = True
                break
        if not found:
            milestones.append(m_data)
    save_account_milestones(acc_id, milestones)
    return m_data

def delete_milestone(acc_id: str, m_id: str):
    """刪除指定重大事件"""
    milestones = get_account_milestones(acc_id)
    milestones = [m for m in milestones if m.get("id") != m_id]
    save_account_milestones(acc_id, milestones)

def get_account_campaign_status(acc_or_id) -> dict:
    """
    計算該帳號當前處於哪一個戰役生命週期階段：
    - 預熱期 (WARMUP): 距離目標重大事件 1 ~ 14 天 (倒數期待期)
    - 引爆日 (LAUNCH_DAY): 距離目標事件 <= 24 小時 (首發狂熱期)
    - 餘波期 (AFTERMATH): 事件發生後 1 ~ 14 天 (開荒攻略與避坑期)
    - 常規巡航 (CRUISE): 目前無緊迫重大事件
    """
    if isinstance(acc_or_id, dict):
        milestones = acc_or_id.get("milestones", [])
    else:
        acc = get_account(acc_or_id)
        milestones = acc.get("milestones", []) if acc else []

    if not milestones:
        return {
            "phase": "CRUISE",
            "milestone": None,
            "days_diff": 999,
            "badge_text": "⚡ 常規巡航",
            "badge_color": "indigo"
        }

    now = datetime.datetime.now()
    today = now.date()
    
    parsed_milestones = []
    for m in milestones:
        t_str = m.get("target_date", "")
        if not t_str:
            continue
        try:
            t_date = datetime.datetime.strptime(t_str.split()[0], "%Y-%m-%d").date()
            diff_days = (t_date - today).days
            parsed_milestones.append((diff_days, t_date, m))
        except Exception:
            continue

    if not parsed_milestones:
        return {
            "phase": "CRUISE",
            "milestone": None,
            "days_diff": 999,
            "badge_text": "⚡ 常規巡航",
            "badge_color": "indigo"
        }

    # 1. 判定引爆日 (當天)
    for diff, t_date, m in parsed_milestones:
        if diff == 0:
            return {
                "phase": "LAUNCH_DAY",
                "milestone": m,
                "days_diff": 0,
                "badge_text": f"🚨 引爆日：{m.get('title', '大事件')} (首發狂熱)",
                "badge_color": "red"
            }

    # 2. 判定即將到來的預熱期 (0 < diff <= 14 天)
    upcoming = [(diff, t_date, m) for diff, t_date, m in parsed_milestones if 0 < diff <= 14]
    if upcoming:
        upcoming.sort(key=lambda x: x[0])
        diff, t_date, m = upcoming[0]
        return {
            "phase": "WARMUP",
            "milestone": m,
            "days_diff": diff,
            "badge_text": f"🔥 預熱期：{m.get('title', '大事件')} (倒數 {diff} 天)",
            "badge_color": "amber"
        }

    # 3. 判定剛發生不久的餘波收割期 (-14 <= diff < 0)
    recent = [(diff, t_date, m) for diff, t_date, m in parsed_milestones if -14 <= diff < 0]
    if recent:
        recent.sort(key=lambda x: x[0], reverse=True)
        diff, t_date, m = recent[0]
        days_since = abs(diff)
        return {
            "phase": "AFTERMATH",
            "milestone": m,
            "days_diff": diff,
            "days_since": days_since,
            "badge_text": f"📈 餘波期：{m.get('title', '大事件')} (上線第 {days_since} 天)",
            "badge_color": "emerald"
        }

    # 4. 遠期重大事件 (diff > 14 天)
    future = [(diff, t_date, m) for diff, t_date, m in parsed_milestones if diff > 14]
    if future:
        future.sort(key=lambda x: x[0])
        diff, t_date, m = future[0]
        return {
            "phase": "CRUISE",
            "milestone": m,
            "days_diff": diff,
            "badge_text": f"📅 鎖定未來大作：{m.get('title', '大事件')} ({diff} 天後)",
            "badge_color": "sky"
        }

    return {
        "phase": "CRUISE",
        "milestone": None,
        "days_diff": 999,
        "badge_text": "⚡ 常規巡航",
        "badge_color": "indigo"
    }

def get_discovered_milestones(acc_id: str) -> list:
    """取得 AI 從貼文雷達探測到但尚未採納的未來事件候選庫"""
    acc_dir = os.path.join(ACCOUNTS_DIR, acc_id)
    fpath = os.path.join(acc_dir, "discovered_milestones.json")
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def add_discovered_milestone(acc_id: str, discovery: dict):
    """AI 自動記錄在貼文中探測到的未來重大時間線索"""
    acc_dir = os.path.join(ACCOUNTS_DIR, acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    fpath = os.path.join(acc_dir, "discovered_milestones.json")
    existing = get_discovered_milestones(acc_id)
    
    # 避免重複標題與日期
    for e in existing:
        if e.get("title") == discovery.get("title") and e.get("target_date") == discovery.get("target_date"):
            return
            
    discovery["id"] = f"disc_{uuid.uuid4().hex[:8]}"
    discovery["discovered_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing.append(discovery)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

def approve_discovered_milestone(acc_id: str, disc_id: str) -> bool:
    """使用者在儀表板一鍵將 AI 探測到的重大事件加入作戰行事曆"""
    acc_dir = os.path.join(ACCOUNTS_DIR, acc_id)
    fpath = os.path.join(acc_dir, "discovered_milestones.json")
    existing = get_discovered_milestones(acc_id)
    target = None
    remaining = []
    for e in existing:
        if e.get("id") == disc_id:
            target = e
        else:
            remaining.append(e)
            
    if target:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(remaining, f, indent=2, ensure_ascii=False)
        add_or_update_milestone(acc_id, {
            "title": target.get("title"),
            "target_date": target.get("target_date"),
            "keywords": target.get("keywords", []),
            "notes": f"由 AI 從貼文 [{target.get('source_title', '')[:30]}] 自動探測發現並採納",
            "auto_discovered": True
        })
        return True
    return False

# ==============================================================================
# 🧬 真人玩家人設 (Human Persona) 與每週防過度擬合覆盤 (Weekly Reflection)
# ==============================================================================

def get_account_persona(acc_id: str) -> dict:
    """獲取指定帳號的玩家真人人設設定"""
    acc = get_account(acc_id)
    if not acc:
        return {}
    default_identity = "每天上班摸魚的大劍老獵犬" if "魔物" in acc.get("name", "") else "嘴硬心軟的排位排骨仔小編"
    default_catch = "假單已經送出去了" if "魔物" in acc.get("name", "") else "誰又在排位搞事"
    return acc.get("persona", {
        "identity": default_identity,
        "tone_style": "幽默、自嘲、熱血、愛用玩家社群黑話與生活感",
        "catchphrase": default_catch,
        "current_bio": ""
    })

def save_account_persona(acc_id: str, persona_data: dict):
    """保存玩家真人人設設定"""
    data = load_data()
    for acc in data.get("accounts", []):
        if acc["id"] == acc_id:
            if "persona" not in acc:
                acc["persona"] = {}
            acc["persona"].update(persona_data)
            break
    save_data(data)

def update_account_bio(acc_id: str, new_bio: str):
    """更新帳號當前已同步之 Bio"""
    data = load_data()
    for acc in data.get("accounts", []):
        if acc["id"] == acc_id:
            if "persona" not in acc:
                acc["persona"] = {}
            acc["persona"]["current_bio"] = new_bio
            break
    save_data(data)

def get_account_reflections(acc_id: str) -> list:
    """獲取指定帳號的 AI 覆盤歷史筆記"""
    acc = get_account(acc_id)
    if not acc:
        return []
    return acc.get("reflections", [])

def add_account_reflection(acc_id: str, reflection_data: dict):
    """記錄一次 AI 週覆盤反思筆記，並更新微調後的策略提示詞"""
    data = load_data()
    reflection_data["id"] = f"refl_{uuid.uuid4().hex[:8]}"
    reflection_data["created_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for acc in data.get("accounts", []):
        if acc["id"] == acc_id:
            if "reflections" not in acc:
                acc["reflections"] = []
            acc["reflections"].append(reflection_data)
            # 若覆盤有微調策略，自動套用至帳號的 strategy_prompt
            if reflection_data.get("tuned_strategy"):
                acc["strategy_prompt"] = reflection_data["tuned_strategy"]
            break
    save_data(data)

DEFAULT_GLOBAL = {
    "AI_BASE_URL": "https://api.relayrouter.ai/v1",
    "AI_API_KEY": "",
    "AI_MODEL": "gemini-2.5-flash"
}

def ensure_accounts_dir():
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)

def normalize_cookie_json(raw_str: str) -> str:
    """
    規格化 Cookie 字串：
    支援 Cookie-Editor 擴充套件匯出的 JSON 陣列、Playwright Storage State 格式，
    自動轉換為 Playwright 所需的 {"cookies": [...], "origins": []} 結構。
    """
    if not raw_str or not raw_str.strip():
        return ""
    
    clean_str = raw_str.strip()
    try:
        data = json.loads(clean_str)
        if isinstance(data, list):
            normalized_cookies = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                cookie = {
                    "name": item.get("name", ""),
                    "value": item.get("value", ""),
                    "domain": item.get("domain", ""),
                    "path": item.get("path", "/"),
                    "httpOnly": bool(item.get("httpOnly", False)),
                    "secure": bool(item.get("secure", False)),
                }
                same_site = item.get("sameSite")
                if same_site:
                    s = str(same_site).lower()
                    if "no_restriction" in s or "none" in s:
                        cookie["sameSite"] = "None"
                    elif "lax" in s:
                        cookie["sameSite"] = "Lax"
                    elif "strict" in s:
                        cookie["sameSite"] = "Strict"
                if "expirationDate" in item and item["expirationDate"]:
                    try:
                        cookie["expires"] = int(item["expirationDate"])
                    except Exception:
                        pass
                normalized_cookies.append(cookie)
            return json.dumps({"cookies": normalized_cookies, "origins": []}, indent=2, ensure_ascii=False)
        elif isinstance(data, dict):
            if "cookies" in data and isinstance(data["cookies"], list):
                data.setdefault("origins", [])
                return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        pass
    
    return clean_str

def get_global_cookie(platform: str) -> dict:
    """獲取全域爬蟲憑證狀態"""
    filename = "x_session.json" if platform == "x" else "facebook_scraper_session.json"
    target_path = os.path.join(BASE_DIR, filename)
    
    # 針對 facebook_scraper，若無專用檔但有 facebook_session.json，也可相容檢視
    if platform == "facebook_scraper" and not os.path.exists(target_path):
        fb_default = os.path.join(BASE_DIR, "facebook_session.json")
        if os.path.exists(fb_default):
            target_path = fb_default

    if os.path.exists(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                data = json.loads(content)
                cookies = data.get("cookies", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                return {
                    "has_session": True,
                    "cookies_count": len(cookies),
                    "length": len(content),
                    "content": content
                }
        except Exception:
            return {"has_session": True, "cookies_count": 0, "length": 0, "content": ""}
    return {"has_session": False, "cookies_count": 0, "length": 0, "content": ""}

def save_global_cookie(platform: str, cookie_data_str: str) -> bool:
    """儲存並規格化全域爬蟲憑證"""
    normalized = normalize_cookie_json(cookie_data_str)
    filename = "x_session.json" if platform == "x" else "facebook_scraper_session.json"
    target_path = os.path.join(BASE_DIR, filename)
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(normalized)
    
    # 若是 fb scraper 且根目錄沒有 facebook_session.json，同步備份一份
    if platform == "facebook_scraper":
        fb_default = os.path.join(BASE_DIR, "facebook_session.json")
        if not os.path.exists(fb_default):
            with open(fb_default, "w", encoding="utf-8") as f:
                f.write(normalized)
    return True

def load_data():
    ensure_accounts_dir()
    if not os.path.exists(ACCOUNTS_CONFIG_FILE):
        # 檢查並自動從舊版 config.json 與 threads_session.json 進行無痛遷移
        migrate_from_legacy()

    if not os.path.exists(ACCOUNTS_CONFIG_FILE) and os.path.exists(os.path.join(ACCOUNTS_DIR, "accounts.example.json")):
        try:
            with open(os.path.join(ACCOUNTS_DIR, "accounts.example.json"), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    
    if os.path.exists(ACCOUNTS_CONFIG_FILE):
        try:
            with open(ACCOUNTS_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "global_settings": DEFAULT_GLOBAL.copy(),
        "accounts": []
    }

def save_data(data):
    ensure_accounts_dir()
    with open(ACCOUNTS_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def migrate_from_legacy():
    """將單帳號時期的 config.json、threads_session.json 與 posted_ids.json 無痛升級至多帳號格式"""
    legacy_config_file = os.path.join(BASE_DIR, "config.json")
    legacy_session_file = os.path.join(BASE_DIR, "threads_session.json")
    legacy_history_file = os.path.join(BASE_DIR, "posted_ids.json")

    global_settings = DEFAULT_GLOBAL.copy()
    initial_accounts = []

    if os.path.exists(legacy_config_file):
        try:
            with open(legacy_config_file, "r", encoding="utf-8") as f:
                legacy_cfg = json.load(f)
            
            global_settings["AI_BASE_URL"] = legacy_cfg.get("AI_BASE_URL", DEFAULT_GLOBAL["AI_BASE_URL"])
            global_settings["AI_API_KEY"] = legacy_cfg.get("AI_API_KEY", "")
            global_settings["AI_MODEL"] = legacy_cfg.get("AI_MODEL", DEFAULT_GLOBAL["AI_MODEL"])

            # 遷移成第一個帳號工作台
            acc_id = "acc_primary"
            acc_dir = os.path.join(ACCOUNTS_DIR, acc_id)
            os.makedirs(acc_dir, exist_ok=True)

            # 遷移 Session
            if os.path.exists(legacy_session_file):
                with open(legacy_session_file, "r", encoding="utf-8") as sf:
                    session_content = sf.read()
                with open(os.path.join(acc_dir, "session.json"), "w", encoding="utf-8") as sf:
                    sf.write(session_content)

            # 遷移歷史發文
            history = []
            if os.path.exists(legacy_history_file):
                with open(legacy_history_file, "r", encoding="utf-8") as hf:
                    history = json.load(hf)
            with open(os.path.join(acc_dir, "history.json"), "w", encoding="utf-8") as hf:
                json.dump(history, hf, indent=2, ensure_ascii=False)

            account_name = legacy_cfg.get("GAME_NAME", "主帳號")
            if "Monster Hunter" in account_name:
                account_name = "dinosaur.56467484 (魔物獵人)"

            initial_accounts.append({
                "id": acc_id,
                "name": account_name,
                "enabled": True,
                "target_region": legacy_cfg.get("TARGET_REGION", "台灣 (繁體中文)"),
                "game_name": legacy_cfg.get("GAME_NAME", "Monster Hunter Wilds"),
                "source_platform": legacy_cfg.get("SOURCE_PLATFORM", "Reddit"),
                "subreddit": legacy_cfg.get("SUBREDDIT", "MonsterHunter"),
                "min_upvotes": int(legacy_cfg.get("MIN_UPVOTES", 100)),
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            print(f"舊版遷移發生警告: {e}")

    save_data({
        "global_settings": global_settings,
        "accounts": initial_accounts
    })

def get_global_settings():
    data = load_data()
    return data.get("global_settings", DEFAULT_GLOBAL)

def save_global_settings(settings):
    data = load_data()
    data["global_settings"].update(settings)
    save_data(data)

def compute_next_run(acc: dict) -> str:
    """計算該帳號下一次自動執行的時間字串 (YYYY-MM-DD HH:MM:SS)"""
    schedule_type = acc.get("schedule_type", "interval")
    now = datetime.datetime.now()

    if schedule_type == "manual":
        return ""
    
    if schedule_type == "interval":
        mins = int(acc.get("interval_minutes") or 180)
        next_dt = now + datetime.timedelta(minutes=mins)
        return next_dt.strftime("%Y-%m-%d %H:%M:%S")

    if schedule_type == "fixed_times":
        raw_times = acc.get("fixed_times", "12:30, 18:30, 22:00")
        parts = [t.strip() for t in raw_times.replace("，", ",").split(",") if t.strip()]
        
        candidates = []
        for p in parts:
            try:
                h, m = map(int, p.split(":"))
                dt_today = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if dt_today > now:
                    candidates.append(dt_today)
                else:
                    candidates.append(dt_today + datetime.timedelta(days=1))
            except Exception:
                continue
        
        if candidates:
            candidates.sort()
            return candidates[0].strftime("%Y-%m-%d %H:%M:%S")
        
        return (now + datetime.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

    return ""

def get_due_accounts() -> list:
    """找出目前所有已啟用且排程時間已到達的帳號"""
    accounts = get_accounts()
    due = []
    now = datetime.datetime.now()
    for acc in accounts:
        if not acc.get("enabled", True):
            continue
        if acc.get("schedule_type") == "manual":
            continue
        next_run_str = acc.get("next_run")
        if not next_run_str:
            continue
        try:
            next_run_dt = datetime.datetime.strptime(next_run_str, "%Y-%m-%d %H:%M:%S")
            if now >= next_run_dt:
                due.append(acc)
        except Exception:
            continue
    return due

def mark_account_run_completed(acc_id: str):
    """更新帳號最後執行時間與推算下一次排程時間"""
    data = load_data()
    for acc in data.get("accounts", []):
        if acc["id"] == acc_id:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            acc["last_run"] = now_str
            acc["next_run"] = compute_next_run(acc)
            break
    save_data(data)

def get_accounts():
    data = load_data()
    accounts = data.get("accounts", [])
    updated = False
    for acc in accounts:
        acc.setdefault("target_platform", "Threads")
        if "source_platforms" not in acc:
            old_src = acc.get("source_platform", "Reddit")
            acc["source_platforms"] = [old_src] if old_src else ["Reddit"]
            updated = True
        
        acc.setdefault("discovery_mode", "rising")
        acc.setdefault("strategy_prompt", "目標是最大化粉絲與關注度，優先挑選該領域最有料、最好笑、最具社群傳播力的即時爆文。")
        acc.setdefault("schedule_type", "interval")
        acc.setdefault("interval_minutes", 180)
        acc.setdefault("fixed_times", "12:30, 18:30, 22:00")
        acc.setdefault("enable_fast_track", True)
        acc.setdefault("fast_track_min_upvotes", 300)
        acc.setdefault("cooldown_minutes", 45)
        acc.setdefault("last_run", "")
        acc.setdefault("milestones", [])
        acc["campaign_status"] = get_account_campaign_status(acc)
        acc.setdefault("persona", {
            "identity": "每天上班摸魚的大劍老獵犬" if "魔物" in acc.get("name", "") else "嘴硬心軟的排位排骨仔小編",
            "tone_style": "幽默、自嘲、熱血、愛用玩家社群黑話與生活感",
            "catchphrase": "假單已經送出去了" if "魔物" in acc.get("name", "") else "誰又在排位搞事",
            "current_bio": ""
        })
        acc.setdefault("reflections", [])
        acc.setdefault("bio_auto_update", True)
        acc.setdefault("bio_update_time", "09:00")
        acc.setdefault("bio_last_updated_date", "")
        if not acc.get("next_run") and acc.get("schedule_type") != "manual":
            acc["next_run"] = compute_next_run(acc)
            updated = True

    if updated:
        save_data(data)
    return accounts

def get_account(acc_id):
    for acc in get_accounts():
        if acc["id"] == acc_id:
            return acc
    return None

def save_account(account_data, session_data_str=None):
    data = load_data()
    accounts = data.get("accounts", [])
    acc_id = account_data.get("id")

    is_new = False
    if not acc_id:
        acc_id = f"acc_{uuid.uuid4().hex[:8]}"
        account_data["id"] = acc_id
        account_data["created_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        is_new = True

    # 確保帳號資料夾
    acc_dir = os.path.join(ACCOUNTS_DIR, acc_id)
    os.makedirs(acc_dir, exist_ok=True)

    # 儲存 Session 檔案 (自動規格化)
    if session_data_str and session_data_str.strip():
        normalized_str = normalize_cookie_json(session_data_str)
        with open(os.path.join(acc_dir, "session.json"), "w", encoding="utf-8") as f:
            f.write(normalized_str)

    # 規格化多來源平台與排程
    if "source_platforms" in account_data:
        if isinstance(account_data["source_platforms"], str):
            account_data["source_platforms"] = [account_data["source_platforms"]]
        if account_data["source_platforms"]:
            account_data["source_platform"] = account_data["source_platforms"][0]
    
    # 動態計算下一次執行時間
    account_data["next_run"] = compute_next_run(account_data)

    if is_new:
        accounts.append(account_data)
    else:
        for idx, item in enumerate(accounts):
            if item["id"] == acc_id:
                accounts[idx].update(account_data)
                break

    data["accounts"] = accounts
    save_data(data)
    return acc_id

def delete_account(acc_id):
    data = load_data()
    accounts = [a for a in data.get("accounts", []) if a["id"] != acc_id]
    data["accounts"] = accounts
    save_data(data)
    
    # 刪除資料夾
    acc_dir = os.path.join(ACCOUNTS_DIR, acc_id)
    if os.path.exists(acc_dir):
        import shutil
        try:
            shutil.rmtree(acc_dir)
        except Exception:
            pass

def get_account_session_path(acc_id):
    path = os.path.join(ACCOUNTS_DIR, acc_id, "session.json")
    return path if os.path.exists(path) else None

def get_account_session_content(acc_id):
    path = get_account_session_path(acc_id)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""

def get_account_history(acc_id):
    path = os.path.join(ACCOUNTS_DIR, acc_id, "history.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def add_account_history(acc_id, post_id):
    history = get_account_history(acc_id)
    if post_id not in history:
        history.append(post_id)
    acc_dir = os.path.join(ACCOUNTS_DIR, acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    with open(os.path.join(acc_dir, "history.json"), "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def update_account_status(acc_id, step: str, message: str, state: str = "RUNNING"):
    acc_dir = os.path.join(ACCOUNTS_DIR, acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    payload = {
        "state": state,
        "step": step,
        "message": message,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(os.path.join(acc_dir, "status.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"[{acc_id}][{state}] {step}: {message}")

def get_account_status(acc_id):
    path = os.path.join(ACCOUNTS_DIR, acc_id, "status.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"state": "IDLE", "step": "待命中", "message": "尚未發起執行任務"}

def record_account_error(acc_id, step: str, err: Exception):
    acc_dir = os.path.join(ACCOUNTS_DIR, acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    payload = {
        "status": "FAILED",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "failed_step": step,
        "error_message": str(err),
        "traceback": traceback.format_exc()
    }
    with open(os.path.join(acc_dir, "error.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    update_account_status(acc_id, step, f"執行失敗: {str(err)}", state="FAILED")
    print(f"\n❌ [{acc_id}] 錯誤已捕捉並記錄至主控台：[{step}] {str(err)}")

def get_account_error(acc_id):
    path = os.path.join(ACCOUNTS_DIR, acc_id, "error.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"status": "SUCCESS", "message": "目前無任何錯誤紀錄，帳號運作正常。"}
