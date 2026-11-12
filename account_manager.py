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

DEFAULT_GLOBAL = {
    "AI_BASE_URL": "https://api.relayrouter.ai/v1",
    "AI_API_KEY": "",
    "AI_MODEL": "gemini-2.5-flash"
}

def ensure_accounts_dir():
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)

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

def get_accounts():
    data = load_data()
    accounts = data.get("accounts", [])
    for acc in accounts:
        acc.setdefault("target_platform", "Threads")
        acc.setdefault("source_platform", "Reddit")
        acc.setdefault("discovery_mode", "rising")
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

    # 儲存 Session 檔案
    if session_data_str and session_data_str.strip():
        with open(os.path.join(acc_dir, "session.json"), "w", encoding="utf-8") as f:
            f.write(session_data_str.strip())

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
