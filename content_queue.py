import os
import json
import datetime
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUEUE_FILE = os.path.join(BASE_DIR, "content_queue.json")
MAX_QUEUE_CAPACITY = 20

def load_queue() -> List[Dict[str, Any]]:
    if not os.path.exists(QUEUE_FILE):
        return []
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ 載入 content_queue.json 失敗: {e}")
        return []

def save_queue(queue: List[Dict[str, Any]]):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

def enqueue_candidates(candidates: List[Dict[str, Any]], history_ids: set) -> int:
    """
    將通過規則庫審查的優質素材加入素材儲備庫 (Buffer Queue)
    自動去重、依攻略優先級與熱度排序，並控制在容量上限內防爆
    """
    queue = load_queue()
    existing_ids = {item["id"] for item in queue}
    added_count = 0

    for post in candidates:
        p_id = post.get("id")
        if not p_id or p_id in history_ids or p_id in existing_ids:
            continue

        entry = {
            "id": p_id,
            "title": post.get("title", ""),
            "full_content": post.get("full_content", ""),
            "source_platform": post.get("source_platform", "未知"),
            "media_type": post.get("media_type", "TEXT"),
            "media_url": post.get("media_url"),
            "upvotes": post.get("upvotes", 0),
            "replies_count": post.get("replies_count", 0),
            "is_priority_guide": post.get("is_priority_guide", False),
            "priority_reason": post.get("priority_reason", ""),
            "enqueued_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        queue.append(entry)
        existing_ids.add(p_id)
        added_count += 1

    # 排序：攻略乾貨絕對優先 (True 排前面)，其餘依社群熱度降序排列
    queue.sort(key=lambda x: (x.get("is_priority_guide", False), x.get("upvotes", 0)), reverse=True)

    # 防爆機制：保持最新且最優質的 MAX_QUEUE_CAPACITY 篇
    if len(queue) > MAX_QUEUE_CAPACITY:
        queue = queue[:MAX_QUEUE_CAPACITY]

    save_queue(queue)
    return added_count

def pop_next_post() -> Optional[Dict[str, Any]]:
    """取出儲備庫中最頂級、最合適的一篇素材以供定點發布"""
    queue = load_queue()
    if not queue:
        return None
    next_post = queue.pop(0)
    save_queue(queue)
    return next_post

def remove_from_queue(post_id: str) -> bool:
    """手動從素材庫中剔除不喜歡的素材"""
    queue = load_queue()
    orig_len = len(queue)
    queue = [p for p in queue if p.get("id") != post_id]
    if len(queue) != orig_len:
        save_queue(queue)
        return True
    return False

def get_queue_preview() -> List[Dict[str, Any]]:
    return load_queue()
