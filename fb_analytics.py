import os
import sys
import json
import random
import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GOLDEN_HOURS = [12, 13, 18, 19, 20, 21, 22, 23]


def _now_tw() -> datetime.datetime:
    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz_tw)


def _acc_file(acc_id: str, filename: str) -> str:
    acc_dir = os.path.join(BASE_DIR, "accounts", acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    return os.path.join(acc_dir, filename)


def load_fb_metrics(acc_id: str) -> list:
    fpath = _acc_file(acc_id, "fb_post_metrics.json")
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_fb_metrics(acc_id: str, metrics: list):
    fpath = _acc_file(acc_id, "fb_post_metrics.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(metrics[-300:], f, indent=2, ensure_ascii=False)


def record_fb_post_metric(acc_id: str, entry: dict):
    """記錄每次 FB 社團發文的時間點、目標社團、文案與後續互動數據"""
    now = _now_tw()
    entry.setdefault("posted_at", now.strftime("%Y-%m-%d %H:%M:%S"))
    entry.setdefault("hour", now.hour)
    entry.setdefault("likes", 0)
    entry.setdefault("comments", 0)
    metrics = load_fb_metrics(acc_id)
    metrics.append(entry)
    save_fb_metrics(acc_id, metrics)


def analyze_top_hours_last_week(acc_id: str, now_dt: datetime.datetime = None) -> list:
    """
    分析過去 7 天 (上一週) 的 FB 貼文表現，計算互動權重最高的前 8 個小時區間；
    若樣本不足則以台灣遊戲買賣社團黃金活躍時段平滑補齊。
    """
    now = now_dt or _now_tw()
    cutoff = now.replace(tzinfo=None) - datetime.timedelta(days=7)
    metrics = load_fb_metrics(acc_id)

    hour_scores = {}
    for m in metrics:
        ts_str = m.get("posted_at", "")
        try:
            dt = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            if dt < cutoff:
                continue
        except Exception:
            continue
        hr = int(m.get("hour", dt.hour))
        score = 1 + int(m.get("likes", 0)) + int(m.get("comments", 0)) * 3
        hour_scores[hr] = hour_scores.get(hr, 0) + score

    ranked = [hr for hr, _ in sorted(hour_scores.items(), key=lambda x: x[1], reverse=True)]
    for fallback_hr in DEFAULT_GOLDEN_HOURS:
        if fallback_hr not in ranked:
            ranked.append(fallback_hr)
    return ranked[:8]


def get_or_init_daily_4_slots(acc_id: str, target_groups: list, now_dt: datetime.datetime = None) -> dict:
    """
    每日產生 4 個位於上週熱門活躍時段內的隨機發文時間點 (格式 HH:MM)，
    彼此間隔至少 90 分鐘並輪替分配至目標 FB 社團。同日重複呼叫維持冪等。
    """
    now = now_dt or _now_tw()
    today_str = now.strftime("%Y-%m-%d")
    sched_path = _acc_file(acc_id, "fb_daily_schedule.json")

    if os.path.exists(sched_path):
        try:
            with open(sched_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if existing.get("date") == today_str and len(existing.get("slots", [])) == 4:
                    return existing
        except Exception:
            pass

    top_hours = analyze_top_hours_last_week(acc_id, now_dt=now)
    candidate_minutes = []
    for hr in top_hours:
        # 每個熱門小時區間挑選 1 個隨機分鐘
        candidate_minutes.append(hr * 60 + random.randint(2, 55))

    random.shuffle(candidate_minutes)
    chosen_mins = []
    for m_val in sorted(candidate_minutes):
        if all(abs(m_val - prev) >= 90 for prev in chosen_mins):
            chosen_mins.append(m_val)
        if len(chosen_mins) == 4:
            break

    # 若候選集中間隔不足 90 分鐘，使用均勻黃金備援時段補滿 4 個
    for fb_min in [11 * 60 + random.randint(5, 45), 14 * 60 + random.randint(5, 45),
                   19 * 60 + random.randint(5, 45), 22 * 60 + random.randint(5, 45)]:
        if len(chosen_mins) >= 4:
            break
        if all(abs(fb_min - prev) >= 90 for prev in chosen_mins):
            chosen_mins.append(fb_min)

    chosen_mins.sort()
    groups = list(target_groups) if target_groups else []
    if groups:
        random.shuffle(groups)

    slots = []
    for idx, total_min in enumerate(chosen_mins[:4]):
        hh, mm = divmod(total_min, 60)
        assigned_group = groups[idx % len(groups)] if groups else ""
        slots.append({
            "slot_index": idx,
            "time": f"{hh:02d}:{mm:02d}",
            "group_url": assigned_group,
            "status": "PENDING",
            "executed_at": ""
        })

    schedule_data = {
        "date": today_str,
        "top_hours_used": top_hours,
        "slots": slots
    }
    with open(sched_path, "w", encoding="utf-8") as f:
        json.dump(schedule_data, f, indent=2, ensure_ascii=False)
    print(f"📅 [FB 排程分析] 已依上週熱門時段 {top_hours} 產生今日 4 個隨機發文時間: {[s['time'] for s in slots]}")
    return schedule_data


def get_due_slot(acc_id: str, target_groups: list, now_dt: datetime.datetime = None) -> dict:
    """檢查目前是否已到達今日 4 個隨機時段中的下一個未執行時段"""
    now = now_dt or _now_tw()
    sched = get_or_init_daily_4_slots(acc_id, target_groups, now_dt=now)
    now_hhmm = now.strftime("%H:%M")

    for slot in sched.get("slots", []):
        if slot.get("status") == "PENDING" and slot.get("time", "99:99") <= now_hhmm:
            return slot
    return None


def mark_slot_completed(acc_id: str, slot_index: int, status: str = "DONE"):
    sched_path = _acc_file(acc_id, "fb_daily_schedule.json")
    if not os.path.exists(sched_path):
        return
    try:
        with open(sched_path, "r", encoding="utf-8") as f:
            sched = json.load(f)
        for s in sched.get("slots", []):
            if s.get("slot_index") == slot_index:
                s["status"] = status
                s["executed_at"] = _now_tw().strftime("%Y-%m-%d %H:%M:%S")
                break
        with open(sched_path, "w", encoding="utf-8") as f:
            json.dump(sched, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ [FB 排程更新] 寫入失敗: {e}")
