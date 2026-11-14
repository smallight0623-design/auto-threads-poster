import os
import json
import datetime
from typing import List, Dict, Any, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_FILE = os.path.join(BASE_DIR, "rules.json")
EXCEPTIONS_FILE = os.path.join(BASE_DIR, "daily_exceptions.json")

def load_rules() -> Dict[str, Any]:
    if not os.path.exists(RULES_FILE):
        return {"version": "1.0.0", "rules": []}
    try:
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ 載入 rules.json 失敗: {e}")
        return {"version": "1.0.0", "rules": []}

def save_rules(rules_data: Dict[str, Any]):
    rules_data["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules_data, f, ensure_ascii=False, indent=2)

def load_exceptions() -> List[Dict[str, Any]]:
    if not os.path.exists(EXCEPTIONS_FILE):
        return []
    try:
        with open(EXCEPTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ 載入 daily_exceptions.json 失敗: {e}")
        return []

def save_exceptions(exceptions: List[Dict[str, Any]]):
    with open(EXCEPTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(exceptions, f, ensure_ascii=False, indent=2)

def add_exception(post: Dict[str, Any], rule_id: str, reason: str, flags: List[str] = None):
    exs = load_exceptions()
    # 避免重複記錄同一貼文
    if any(e.get("post_id") == post.get("id") for e in exs):
        return
    
    ex_entry = {
        "exception_id": f"EX-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{post.get('id', 'unk')[:6]}",
        "post_id": post.get("id"),
        "title": post.get("title", ""),
        "source_platform": post.get("source_platform", "未知"),
        "media_type": post.get("media_type", "TEXT"),
        "media_url": post.get("media_url"),
        "permalink": post.get("permalink", ""),
        "full_content": post.get("full_content", "")[:300],
        "score": post.get("upvotes", 0),
        "rule_id": rule_id,
        "reason": reason,
        "flags": flags or [],
        "status": "PENDING_REVIEW",  # PENDING_REVIEW, APPROVED, REJECTED
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "resolution_note": ""
    }
    exs.append(ex_entry)
    save_exceptions(exs)
    print(f"🚩 [Rule Engine] 貼文 [{post.get('id')}] 觸發例外標註 ({rule_id}): {reason}")

def evaluate_post(post: Dict[str, Any], rules_data: Dict[str, Any] = None) -> Tuple[str, str, str]:
    """
    評估單篇貼文：
    回傳 (status, rule_id, reason)
    status 可為:
      - 'PASS': 通過所有規則
      - 'REJECT': 命中淘汰規則
      - 'EXCEPTION': 命中邊界例外規則，需人工裁決
    """
    if not rules_data:
        rules_data = load_rules()

    title_lower = post.get("title", "").lower()
    content_lower = post.get("full_content", "").lower()

    for r in rules_data.get("rules", []):
        if r.get("status") != "ACTIVE":
            continue
        
        cond = r.get("condition", {})
        action = r.get("action", "REJECT")
        
        # 1. 標題/內容關鍵字黑名單
        kw_excludes = [k.lower() for k in cond.get("title_keywords_exclude", [])]
        if any(kw in title_lower or kw in content_lower for kw in kw_excludes):
            if action == "FLAG_EXCEPTION":
                return "EXCEPTION", r.get("id"), r.get("reason")
            return "REJECT", r.get("id"), r.get("reason")

        # 2. 多圖超限
        if cond.get("image_count_gt"):
            img_count = post.get("image_count", 1 if post.get("media_type") == "IMAGE" else 0)
            if img_count > cond.get("image_count_gt"):
                if action == "FLAG_EXCEPTION":
                    return "EXCEPTION", r.get("id"), r.get("reason")
                return "REJECT", r.get("id"), r.get("reason")

    return "PASS", "", "通過所有規則檢驗"

def filter_candidates(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    批次篩選候選貼文：
    回傳 (passed_list, rejected_list, exceptions_list)
    """
    rules_data = load_rules()
    passed = []
    rejected = []
    exceptions = []

    for post in candidates:
        status, rule_id, reason = evaluate_post(post, rules_data)
        post_copy = dict(post)
        post_copy["eval_status"] = status
        post_copy["eval_rule_id"] = rule_id
        post_copy["eval_reason"] = reason

        if status == "PASS":
            passed.append(post_copy)
        elif status == "EXCEPTION":
            exceptions.append(post_copy)
            add_exception(post, rule_id, reason)
        else:
            rejected.append(post_copy)

    print(f"📊 [Rule Engine 篩選結果]: 候選 {len(candidates)} 篇 ➔ 通過 {len(passed)} 篇 ｜ 淘汰 {len(rejected)} 篇 ｜ 例外標註 {len(exceptions)} 篇")
    return passed, rejected, exceptions
