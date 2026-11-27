import os
import sys
import json
import time
import datetime
import requests

import account_manager
import ai_engine

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_FILE = os.path.join(BASE_DIR, "products.json")
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/smallight0623-design/auto-threads-poster/main"
GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def load_products() -> list:
    if os.path.exists(PRODUCTS_FILE):
        try:
            with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ [IG/FB 型錄] 讀取 products.json 失敗: {e}")
    return []


def save_products(products: list):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)


def resolve_public_image_url(image_url_or_path: str) -> str:
    """
    Meta Instagram Graph API 要求圖片必須為公開可存取的 HTTPS URL。
    若傳入本地相對路徑 (如 products/media/acc_001.jpg)，自動轉換為本公開倉庫的 GitHub Raw URL。
    """
    val = (image_url_or_path or "").strip()
    if not val:
        return ""
    if val.startswith("http://") or val.startswith("https://"):
        return val
    clean_rel = val.replace("\\", "/").lstrip("./")
    return f"{GITHUB_RAW_BASE}/{clean_rel}"


def _load_json_state(acc_id: str, filename: str, default):
    acc_dir = os.path.join(BASE_DIR, "accounts", acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    fpath = os.path.join(acc_dir, filename)
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _save_json_state(acc_id: str, filename: str, data):
    acc_dir = os.path.join(BASE_DIR, "accounts", acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    fpath = os.path.join(acc_dir, filename)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _get_ig_credentials(acc: dict) -> tuple:
    token = (os.getenv("IG_ACCESS_TOKEN") or acc.get("ig_access_token") or "").strip()
    ig_user_id = (os.getenv("IG_USER_ID") or acc.get("ig_user_id") or "").strip()
    return token, ig_user_id


def publish_ig_product_post(acc_id: str, product: dict, token: str, ig_user_id: str) -> dict:
    """透過 Meta Instagram Graph API 發布固定格式遊戲帳號圖文貼文"""
    image_url = resolve_public_image_url(product.get("image_url", ""))
    if not image_url:
        return {"success": False, "error": "商品缺少有效的公開圖片 URL 或 products/media/ 路徑"}

    caption = ai_engine.format_ig_game_account_post(product)

    # 1. 建立 Media Container
    create_url = f"{GRAPH_API_BASE}/{ig_user_id}/media"
    resp = requests.post(
        create_url,
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": token
        },
        timeout=30
    )
    if resp.status_code != 200:
        return {"success": False, "error": f"建立 IG Media Container 失敗: {resp.text}"}

    creation_id = resp.json().get("id")
    if not creation_id:
        return {"success": False, "error": f"未取得 creation_id: {resp.text}"}

    # 2. 等待容器處理完成（通常 2~8 秒）
    for _ in range(6):
        status_res = requests.get(
            f"{GRAPH_API_BASE}/{creation_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=15
        )
        if status_res.status_code == 200:
            code = status_res.json().get("status_code")
            if code in ("FINISHED", None):
                break
            if code == "ERROR":
                return {"success": False, "error": f"IG 圖片處理失敗: {status_res.text}"}
        time.sleep(2)

    # 3. 正式發布貼文
    pub_url = f"{GRAPH_API_BASE}/{ig_user_id}/media_publish"
    pub_resp = requests.post(
        pub_url,
        data={"creation_id": creation_id, "access_token": token},
        timeout=30
    )
    if pub_resp.status_code != 200:
        return {"success": False, "error": f"發布 IG 貼文失敗: {pub_resp.text}"}

    media_id = pub_resp.json().get("id")
    print(f"📸 [IG Manager] 成功發布商品貼文 [{product.get('id')}] ➔ IG Media ID: {media_id}")
    return {"success": True, "media_id": media_id, "caption": caption}


def reply_ig_comments(acc_id: str, token: str, ig_user_id: str, products: list, config: dict) -> int:
    """巡檢近期 IG 貼文底下留言並以 AI 自動回覆銷售問題"""
    media_res = requests.get(
        f"{GRAPH_API_BASE}/{ig_user_id}/media",
        params={"fields": "id,caption,timestamp", "limit": 10, "access_token": token},
        timeout=20
    )
    if media_res.status_code != 200:
        print(f"⚠️ [IG 留言巡檢] 讀取貼文清單失敗: {media_res.text}")
        return 0

    replied_map = _load_json_state(acc_id, "ig_replied_comments.json", {})
    replied_count = 0

    for media in media_res.json().get("data", []):
        m_id = media.get("id")
        cmt_res = requests.get(
            f"{GRAPH_API_BASE}/{m_id}/comments",
            params={"fields": "id,text,username,from,timestamp", "limit": 20, "access_token": token},
            timeout=15
        )
        if cmt_res.status_code != 200:
            continue

        for cmt in cmt_res.json().get("data", []):
            c_id = cmt.get("id")
            if not c_id or c_id in replied_map:
                continue
            from_id = (cmt.get("from") or {}).get("id", "")
            if from_id == ig_user_id:
                continue

            c_text = (cmt.get("text") or "").strip()
            if not c_text:
                continue

            reply_text = ai_engine.generate_sales_support_reply(
                "Instagram 貼文留言", c_text, products, config
            )
            if not reply_text:
                continue

            r_post = requests.post(
                f"{GRAPH_API_BASE}/{c_id}/replies",
                data={"message": reply_text, "access_token": token},
                timeout=15
            )
            if r_post.status_code == 200:
                replied_count += 1
                replied_map[c_id] = {
                    "media_id": m_id,
                    "user_text": c_text,
                    "reply_text": reply_text,
                    "replied_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                print(f"💬 [IG 留言回覆] @{cmt.get('username', '買家')}: {c_text[:25]} ➔ {reply_text}")

    _save_json_state(acc_id, "ig_replied_comments.json", replied_map)
    return replied_count


def reply_ig_dms(acc_id: str, token: str, ig_user_id: str, products: list, config: dict) -> int:
    """透過 Instagram Messaging API 巡檢近期對話並自動回覆未讀私訊"""
    conv_res = requests.get(
        f"{GRAPH_API_BASE}/{ig_user_id}/conversations",
        params={
            "platform": "instagram",
            "fields": "id,participants,messages{id,message,from,created_time}",
            "limit": 15,
            "access_token": token
        },
        timeout=20
    )
    if conv_res.status_code != 200:
        print(f"⚠️ [IG 私訊巡檢] 讀取對話失敗: {conv_res.text}")
        return 0

    dm_history = _load_json_state(acc_id, "ig_dm_history.json", {"replied_msg_ids": [], "threads": {}})
    replied_ids = set(dm_history.get("replied_msg_ids", []))
    sent_count = 0

    for conv in conv_res.json().get("data", []):
        messages = (conv.get("messages") or {}).get("data", [])
        if not messages:
            continue

        # Meta 回傳通常為最新訊息在索引 0
        latest = messages[0]
        msg_id = latest.get("id")
        sender_id = (latest.get("from") or {}).get("id", "")
        msg_text = (latest.get("message") or "").strip()

        # 若最新一則是我方自己發出的，或該訊息已回覆過，跳過
        if not msg_id or not sender_id or sender_id == ig_user_id or msg_id in replied_ids or not msg_text:
            continue

        conv_id = conv.get("id", sender_id)
        past_msgs = dm_history.get("threads", {}).get(conv_id, [])

        reply_text = ai_engine.generate_sales_support_reply(
            "Instagram 私訊 (DM)", msg_text, products, config, conversation_history=past_msgs
        )
        if not reply_text:
            continue

        send_res = requests.post(
            f"{GRAPH_API_BASE}/{ig_user_id}/messages",
            json={
                "recipient": {"id": sender_id},
                "message": {"text": reply_text}
            },
            params={"access_token": token},
            timeout=15
        )
        if send_res.status_code == 200:
            sent_count += 1
            replied_ids.add(msg_id)
            past_msgs.append({"role": "buyer", "text": msg_text})
            past_msgs.append({"role": "seller", "text": reply_text})
            dm_history.setdefault("threads", {})[conv_id] = past_msgs[-10:]
            print(f"📩 [IG 私訊回覆] 買家({sender_id}): {msg_text[:25]} ➔ {reply_text}")

    dm_history["replied_msg_ids"] = list(replied_ids)[-500:]
    _save_json_state(acc_id, "ig_dm_history.json", dm_history)
    return sent_count


def handle_meta_webhook_event(payload: dict, acc_id: str = "acc_ig") -> dict:
    """預留標準 Meta Webhook 事件介面（未來升級 Cloudflare Workers / FastAPI 即時秒回時直接調用）"""
    acc = account_manager.get_account(acc_id) or {}
    token, ig_user_id = _get_ig_credentials(acc)
    if not token or not ig_user_id:
        return {"handled": False, "reason": "missing_credentials"}

    products = load_products()
    cfg = account_manager.get_global_settings()
    replied = 0

    for entry in payload.get("entry", []):
        for msg_ev in entry.get("messaging", []):
            sender_id = (msg_ev.get("sender") or {}).get("id")
            text = ((msg_ev.get("message") or {}).get("text") or "").strip()
            if sender_id and sender_id != ig_user_id and text:
                reply = ai_engine.generate_sales_support_reply("Instagram 私訊 (DM)", text, products, cfg)
                if reply:
                    requests.post(
                        f"{GRAPH_API_BASE}/{ig_user_id}/messages",
                        json={"recipient": {"id": sender_id}, "message": {"text": reply}},
                        params={"access_token": token},
                        timeout=10
                    )
                    replied += 1
    return {"handled": True, "replied": replied}


def run_ig_cycle(acc_id: str) -> dict:
    """執行 IG 商業帳號完整營運週期：自動發待售商品 ＋ 回覆貼文留言 ＋ 回覆私訊"""
    acc = account_manager.get_account(acc_id)
    if not acc:
        return {"success": False, "error": f"找不到帳號 {acc_id}"}

    token, ig_user_id = _get_ig_credentials(acc)
    if not token or not ig_user_id:
        print(f"ℹ️ [{acc_id}] 尚未設定 IG_ACCESS_TOKEN / IG_USER_ID，待 Meta Graph API 開通後即可自動啟動 IG 發文與客服。")
        return {"success": False, "skipped": True, "reason": "IG Graph API 尚未開通設定"}

    products = load_products()
    cfg = account_manager.get_global_settings()

    # 1. 檢查是否有尚未發布至 IG 的「可售中」遊戲帳號（且真實圖片已存在或為公開網址）
    ig_posted_map = _load_json_state(acc_id, "ig_posted_products.json", {})
    posted_media_id = None
    for prod in products:
        pid = prod.get("id")
        if prod.get("status", "AVAILABLE").upper() != "AVAILABLE":
            continue
        if pid in ig_posted_map:
            continue
        img_raw = prod.get("image_url", "")
        if not img_raw.startswith("http") and not os.path.exists(os.path.join(BASE_DIR, img_raw)):
            continue
        pub_res = publish_ig_product_post(acc_id, prod, token, ig_user_id)
        if pub_res.get("success"):
            posted_media_id = pub_res.get("media_id")
            ig_posted_map[pid] = {
                "media_id": posted_media_id,
                "posted_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            _save_json_state(acc_id, "ig_posted_products.json", ig_posted_map)
        break  # 每次巡航最多發布一篇商品，避免洗版

    # 2. 自動回覆 IG 貼文留言 & 私訊 DM
    cmt_count = reply_ig_comments(acc_id, token, ig_user_id, products, cfg)
    dm_count = reply_ig_dms(acc_id, token, ig_user_id, products, cfg)

    return {
        "success": True,
        "posted_media_id": posted_media_id,
        "replied_comments": cmt_count,
        "replied_dms": dm_count
    }
