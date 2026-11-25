import os
import json
import datetime
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUEUE_FILE = os.path.join(BASE_DIR, "content_queue.json")
POSTED_HISTORY_FILE = os.path.join(BASE_DIR, "posted_ids.json")
MAX_QUEUE_CAPACITY = 200
TTL_DAYS = 7  # 素材保鮮期：超過 7 天未發布之非突發素材自動過期修剪

def load_posted_history() -> Dict[str, str]:
    """載入已發布貼文歷史紀錄 (ID -> 發布時間)"""
    if not os.path.exists(POSTED_HISTORY_FILE):
        return {}
    try:
        with open(POSTED_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                # 兼容舊版純 ID 陣列
                return {pid: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") for pid in data}
            return data
    except Exception as e:
        print(f"⚠️ 載入 posted_ids.json 失敗: {e}")
        return {}

def save_posted_history(data: Dict[str, str]):
    with open(POSTED_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def record_posted_id(post_id: str):
    """將發布完成之貼文 ID 納入歷史黑名單，保留一週防止再次抓取"""
    data = load_posted_history()
    data[post_id] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 清理超過 7 天之超時過期 ID
    now = datetime.datetime.now()
    cleaned = {}
    for pid, t_str in data.items():
        try:
            dt = datetime.datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
            if (now - dt).days <= TTL_DAYS:
                cleaned[pid] = t_str
        except Exception:
            cleaned[pid] = t_str
    save_posted_history(cleaned)

def is_already_posted(post_id: str) -> bool:
    """檢查貼文是否在過去一週內已被發布過"""
    data = load_posted_history()
    if post_id not in data:
        return False
    t_str = data[post_id]
    try:
        dt = datetime.datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
        return (datetime.datetime.now() - dt).days <= TTL_DAYS
    except Exception:
        return True

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

def determine_timeslot_buckets(post: Dict[str, Any]) -> List[str]:
    """
    依據貼文調性、內容類型與媒體形式，動態劃分最適合發布的黃金時段標籤：
    - morning: 晨間通勤 (08:45, 10:30) - 輕鬆短圖、早晨迷因、日常問候
    - lunch: 午休小憩 (12:15, 14:00) - 實用速食乾貨、趣味神操作、高光短影音
    - afternoon: 午後休閒 (16:00, 18:00) - 二創美術繪圖、趣聞、社群話題
    - evening: 晚間黃金主力開荒 (19:45, 21:15) - 深度配裝、怪物打法攻略、硬核機制、重大版本更新
    - night: 深夜夜貓 (22:45, 23:59) - 貓車自嘲、同溫層夜聊、極限精彩高光
    """
    title = post.get("title", "").lower()
    content = post.get("full_content", "").lower()
    media_type = post.get("media_type", "TEXT")
    is_guide = post.get("is_priority_guide", False)

    # 突發重大情報 / 官方公告 -> 標註 instant，全時段皆可發且享有最高優先級
    breaking_kws = ["官方公告", "維修公告", "緊急維護", "宣傳片", "official trailer", "最新預告", "release date", "正式發售日"]
    if any(kw in title for kw in breaking_kws):
        return ["instant", "morning", "lunch", "afternoon", "evening", "night"]

    buckets = set()
    if is_guide:
        # 攻略乾貨：最適合晚上黃金開荒檔與午休充能檔
        buckets.add("evening")
        buckets.add("lunch")

    if media_type == "VIDEO":
        # 短影音高光：午間、午後摸魚、深夜
        buckets.update(["lunch", "afternoon", "night"])
    elif media_type == "IMAGE":
        # 圖文二創與迷因：晨間通勤、午後放鬆、深夜共鳴
        buckets.update(["morning", "afternoon", "night"])
    else:
        # 純文字討論與心得：午後茶餘飯後、晚間深度開荒、深夜閒聊
        buckets.update(["afternoon", "evening", "night"])

    if not buckets:
        buckets.add("general")
    return sorted(list(buckets))

def get_current_slot_name(dt: Optional[datetime.datetime] = None) -> str:
    """將當前時間映射至 5 大目標黃金時段名稱"""
    if dt is None:
        dt = datetime.datetime.now()
    val = dt.hour * 60 + dt.minute

    if 6 * 60 <= val < 11 * 60 + 30:
        return "morning"       # 06:00 ~ 11:30 (覆蓋 08:45, 10:30)
    elif 11 * 60 + 30 <= val < 15 * 60:
        return "lunch"         # 11:30 ~ 15:00 (覆蓋 12:15, 14:00)
    elif 15 * 60 <= val < 18 * 60 + 45:
        return "afternoon"     # 15:00 ~ 18:45 (覆蓋 16:00, 18:00)
    elif 18 * 60 + 45 <= val < 22 * 60:
        return "evening"       # 18:45 ~ 22:00 (覆蓋 19:45, 21:15)
    else:
        return "night"         # 22:00 ~ 05:59 (覆蓋 22:45, 23:59)

def prune_expired_posts(queue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """清理素材庫中超過 TTL 保鮮期 (7天) 且未被發布的老化素材"""
    now = datetime.datetime.now()
    valid_queue = []
    for item in queue:
        enqueued_time_str = item.get("enqueued_at")
        if enqueued_time_str:
            try:
                enq_dt = datetime.datetime.strptime(enqueued_time_str, "%Y-%m-%d %H:%M:%S")
                if (now - enq_dt).days > TTL_DAYS:
                    continue  # 老化過期剔除
            except Exception:
                pass
        valid_queue.append(item)
    return valid_queue

def enqueue_candidates(candidates: List[Dict[str, Any]], history_ids: set) -> int:
    """
    將通過規則庫審查的優質素材加入素材儲備庫 (Buffer Queue)
    自動去重、分發黃金時段標籤、依攻略優先級與熱度排序，並控制在 200 篇容量上限內防爆
    """
    queue = load_queue()
    queue = prune_expired_posts(queue)
    existing_ids = {item["id"] for item in queue}
    added_count = 0

    for post in candidates:
        p_id = post.get("id")
        if not p_id or p_id in history_ids or p_id in existing_ids or is_already_posted(p_id):
            continue

        timeslot_buckets = determine_timeslot_buckets(post)
        is_instant = "instant" in timeslot_buckets

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
            "instant_priority": is_instant,
            "timeslot_buckets": timeslot_buckets,
            "enqueued_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        queue.append(entry)
        existing_ids.add(p_id)
        added_count += 1

    # 排序：突發最高優先 (instant_priority) -> 圖文並茂/影音優先 (IMAGE/VIDEO) -> 攻略乾貨優先 (is_priority_guide) -> 社群熱度 (upvotes) 降序
    queue.sort(
        key=lambda x: (
            x.get("instant_priority", False),
            x.get("media_type") in ("IMAGE", "VIDEO") and bool(x.get("media_url")),
            x.get("is_priority_guide", False),
            x.get("upvotes", 0)
        ),
        reverse=True
    )

    # 容量防爆機制：嚴格維持在 MAX_QUEUE_CAPACITY (200 篇) 以內
    if len(queue) > MAX_QUEUE_CAPACITY:
        queue = queue[:MAX_QUEUE_CAPACITY]

    save_queue(queue)
    return added_count

def pop_next_post_for_slot(slot_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    從儲備庫挑選出最適合當前時段的一篇頂級素材以供發布：
    1. 突發重大情報 (instant_priority) 絕對優先插隊
    2. 若有指定時段，優先從匹配該時段 (slot_name 或 general) 的候選集挑選最熱門/攻略素材
    3. 【防開天窗降級機制】：若該時段桶子為空，平滑退回全庫最高熱度之素材，絕不漏發
    4. 取出後自素材庫刪除，保持素材庫流動更新
    """
    queue = load_queue()
    if not queue:
        return None

    if slot_name is None:
        slot_name = get_current_slot_name()

    # 檢查是否有突發緊急重大情報
    instant_idx = -1
    for idx, item in enumerate(queue):
        if item.get("instant_priority", False):
            instant_idx = idx
            break

    if instant_idx >= 0:
        chosen = queue.pop(instant_idx)
        save_queue(queue)
        record_posted_id(chosen["id"])
        print(f"🚨 [素材挑選] 觸發【突發重大情報插隊】：{chosen.get('title')[:30]}...")
        return chosen

    # 尋找匹配該時段的候選集
    slot_matches = []
    for idx, item in enumerate(queue):
        buckets = item.get("timeslot_buckets", ["general"])
        if slot_name in buckets or "general" in buckets:
            slot_matches.append((idx, item))

    if slot_matches:
        # 在符合時段的素材中，優先挑選圖文並茂 (IMAGE/VIDEO)，其次攻略優先度與熱度
        slot_matches.sort(
            key=lambda x: (
                x[1].get("media_type") in ("IMAGE", "VIDEO") and bool(x[1].get("media_url")),
                x[1].get("is_priority_guide", False),
                x[1].get("upvotes", 0)
            ),
            reverse=True
        )
        best_idx, chosen = slot_matches[0]
        # 從原始隊列中移除
        queue.pop(best_idx)
        save_queue(queue)
        record_posted_id(chosen["id"])
        print(f"🎯 [素材挑選] 匹配時段【{slot_name}】最佳素材：{chosen.get('title')[:30]}... (👍 {chosen.get('upvotes')})")
        return chosen

    # 【防開天窗降級 Fallback】：該時段無專屬素材，退回全庫綜合排名第一名
    print(f"⚠️ [素材挑選] 時段【{slot_name}】無匹配素材，啟動防開天窗降級機制，提取全庫最高熱度素材...")
    chosen = queue.pop(0)
    save_queue(queue)
    record_posted_id(chosen["id"])
    return chosen

def pop_next_post() -> Optional[Dict[str, Any]]:
    """向後相容：依當前時間自動匹配時段挑選"""
    return pop_next_post_for_slot()

def remove_from_queue(post_id: str) -> bool:
    """手動從素材庫中剔除不合適的素材"""
    queue = load_queue()
    orig_len = len(queue)
    queue = [p for p in queue if p.get("id") != post_id]
    if len(queue) != orig_len:
        save_queue(queue)
        return True
    return False

def get_queue_preview() -> List[Dict[str, Any]]:
    return load_queue()
