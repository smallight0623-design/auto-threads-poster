import os
import sys
import json
import hashlib
import datetime
import asyncio
import requests
from playwright.async_api import async_playwright

import account_manager
import ai_engine
import ig_manager
import fb_analytics

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def _load_state(acc_id: str, filename: str, default):
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


def _save_state(acc_id: str, filename: str, data):
    acc_dir = os.path.join(BASE_DIR, "accounts", acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    fpath = os.path.join(acc_dir, filename)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def reply_fb_page_comments_and_dms(acc_id: str, acc: dict, products: list, config: dict) -> dict:
    """
    透過 Meta Page Graph API 自動回覆 FB 粉專貼文留言與 Messenger 私訊（完全免費、零鎖號風險）。
    需設定 FB_PAGE_ACCESS_TOKEN 與 FB_PAGE_ID。
    """
    page_token = (os.getenv("FB_PAGE_ACCESS_TOKEN") or acc.get("fb_page_access_token") or "").strip()
    page_id = (os.getenv("FB_PAGE_ID") or acc.get("fb_page_id") or "").strip()
    if not page_token or not page_id:
        return {"skipped": True, "comments_replied": 0, "dms_replied": 0}

    replied_cmts = _load_state(acc_id, "fb_replied_comments.json", {})
    dm_state = _load_state(acc_id, "fb_dm_history.json", {"replied_msg_ids": [], "threads": {}})
    replied_msg_ids = set(dm_state.get("replied_msg_ids", []))
    cmt_count = 0
    dm_count = 0

    # 1. 粉專近期貼文留言回覆
    feed_res = requests.get(
        f"{GRAPH_API_BASE}/{page_id}/posts",
        params={"fields": "id,message", "limit": 10, "access_token": page_token},
        timeout=20
    )
    if feed_res.status_code == 200:
        for post in feed_res.json().get("data", []):
            p_id = post.get("id")
            c_res = requests.get(
                f"{GRAPH_API_BASE}/{p_id}/comments",
                params={"fields": "id,message,from", "limit": 20, "access_token": page_token},
                timeout=15
            )
            if c_res.status_code != 200:
                continue
            for cmt in c_res.json().get("data", []):
                c_id = cmt.get("id")
                from_id = (cmt.get("from") or {}).get("id", "")
                msg = (cmt.get("message") or "").strip()
                if not c_id or c_id in replied_cmts or from_id == page_id or not msg:
                    continue
                reply = ai_engine.generate_sales_support_reply("Facebook 粉專留言", msg, products, config)
                if not reply:
                    continue
                post_r = requests.post(
                    f"{GRAPH_API_BASE}/{c_id}/comments",
                    data={"message": reply, "access_token": page_token},
                    timeout=15
                )
                if post_r.status_code == 200:
                    cmt_count += 1
                    replied_cmts[c_id] = {"user_text": msg, "reply_text": reply, "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    # 2. 粉專 Messenger 私訊回覆
    conv_res = requests.get(
        f"{GRAPH_API_BASE}/{page_id}/conversations",
        params={"fields": "id,participants,messages{id,message,from,created_time}", "limit": 15, "access_token": page_token},
        timeout=20
    )
    if conv_res.status_code == 200:
        for conv in conv_res.json().get("data", []):
            msgs = (conv.get("messages") or {}).get("data", [])
            if not msgs:
                continue
            latest = msgs[0]
            m_id = latest.get("id")
            sender_id = (latest.get("from") or {}).get("id", "")
            msg_text = (latest.get("message") or "").strip()
            if not m_id or not sender_id or sender_id == page_id or m_id in replied_msg_ids or not msg_text:
                continue

            conv_id = conv.get("id", sender_id)
            past = dm_state.get("threads", {}).get(conv_id, [])
            reply = ai_engine.generate_sales_support_reply("Facebook Messenger 私訊", msg_text, products, config, conversation_history=past)
            if not reply:
                continue

            send_res = requests.post(
                f"{GRAPH_API_BASE}/me/messages",
                json={"recipient": {"id": sender_id}, "message": {"text": reply}},
                params={"access_token": page_token},
                timeout=15
            )
            if send_res.status_code == 200:
                dm_count += 1
                replied_msg_ids.add(m_id)
                past.append({"role": "buyer", "text": msg_text})
                past.append({"role": "seller", "text": reply})
                dm_state.setdefault("threads", {})[conv_id] = past[-10:]

    _save_state(acc_id, "fb_replied_comments.json", replied_cmts)
    dm_state["replied_msg_ids"] = list(replied_msg_ids)[-500:]
    _save_state(acc_id, "fb_dm_history.json", dm_state)
    return {"skipped": False, "comments_replied": cmt_count, "dms_replied": dm_count}


async def reply_fb_group_comments_playwright(acc_id: str, session_file: str, products: list, config: dict, max_posts: int = 4) -> int:
    """
    巡檢近期在 FB 指定社團發出的賣場貼文底下留言（Playwright 瀏覽器），
    對新買家提問自動回覆引導至粉專私訊／商品細節，並更新貼文讚數與留言數回報 fb_analytics。
    """
    resolved_session = account_manager.materialize_session_file(
        session_file, "FACEBOOK_SESSION_DATA", "facebook_session.json"
    )
    if not resolved_session or not os.path.exists(resolved_session):
        return 0

    metrics = fb_analytics.load_fb_metrics(acc_id)
    target_permalinks = []
    seen = set()
    for m in reversed(metrics):
        plink = m.get("permalink", "")
        if plink and ("/posts/" in plink or "/permalink/" in plink) and plink not in seen:
            seen.add(plink)
            target_permalinks.append(plink)
        if len(target_permalinks) >= max_posts:
            break

    if not target_permalinks:
        return 0

    replied_cmts = _load_state(acc_id, "fb_replied_comments.json", {})
    replied_count = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-notifications"]
        )
        context = await browser.new_context(
            storage_state=resolved_session,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        page = await context.new_page()
        await page.add_init_script("delete Object.getPrototypeOf(navigator).webdriver")

        try:
            for plink in target_permalinks:
                try:
                    await page.goto(plink, wait_until="domcontentloaded", timeout=25000)
                    await asyncio.sleep(3)
                    if "login" in page.url:
                        break

                    # 擷取貼文下的留言元素
                    comments = await page.evaluate(r'''() => {
                        const list = [];
                        const els = Array.from(document.querySelectorAll('div[role="article"]'));
                        // 第一個 article 常為主貼文容器，抓取內部留言區塊
                        for (let i = 1; i < Math.min(els.length, 10); i++) {
                            const txt = (els[i].innerText || '').replace(/\s+/g, ' ').trim();
                            if (txt.length >= 2 && txt.length < 250) {
                                list.push({ index: i, text: txt });
                            }
                        }
                        return list;
                    }''')

                    for c in comments:
                        c_hash = hashlib.md5(f"{plink}::{c['text'][:60]}".encode("utf-8")).hexdigest()[:16]
                        if c_hash in replied_cmts:
                            continue
                        reply = ai_engine.generate_sales_support_reply("Facebook 社團貼文留言", c["text"], products, config)
                        if not reply:
                            continue

                        # 嘗試在該頁留言框填入回覆並送出
                        cmt_box = page.locator("div[role='textbox'][aria-label*='留言'], div[role='textbox'][aria-label*='comment' i]").first
                        if await cmt_box.count() > 0:
                            await cmt_box.click()
                            await page.keyboard.type(reply, delay=15)
                            await page.keyboard.press("Enter")
                            await asyncio.sleep(2.5)
                            replied_count += 1
                            replied_cmts[c_hash] = {
                                "permalink": plink,
                                "user_text": c["text"],
                                "reply_text": reply,
                                "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            print(f"💬 [FB 社團留言回覆] {c['text'][:25]} ➔ {reply}")
                            break  # 每篇每輪最多回 1 則以維持擬真安全節奏
                except Exception as pe:
                    print(f"⚠️ [FB 社團留言巡檢] {plink} 例外: {pe}")
        finally:
            await browser.close()

    _save_state(acc_id, "fb_replied_comments.json", replied_cmts)
    return replied_count


async def run_fb_commerce_cycle(acc_id: str) -> dict:
    """
    Facebook 商業完整營運週期：
    1. 檢查上週熱門時段每日 4 個隨機發文排程，到期則選取可用商品於對應社團發布 AI 差異化文案
    2. 執行 FB 粉專 API 留言/私訊回覆 ＋ 社團貼文 Playwright 留言巡檢
    """
    import facebook_playwright

    acc = account_manager.get_account(acc_id)
    if not acc:
        return {"success": False, "error": f"找不到帳號 {acc_id}"}

    products = ig_manager.load_products()
    avail_products = [p for p in products if str(p.get("status", "AVAILABLE")).upper() == "AVAILABLE"]
    cfg = account_manager.get_global_settings()
    session_file = os.path.join(BASE_DIR, "accounts", acc_id, "facebook_session.json")

    # 彙總所有目標社團清單 (優先讀取帳號設定，其次讀取商品內建 target_fb_groups)
    target_groups = list(acc.get("target_fb_groups") or [])
    if not target_groups:
        for p in avail_products:
            for g in (p.get("target_fb_groups") or []):
                if g not in target_groups:
                    target_groups.append(g)

    posted_group_res = None
    due_slot = fb_analytics.get_due_slot(acc_id, target_groups) if target_groups else None

    if due_slot and avail_products:
        slot_idx = due_slot["slot_index"]
        target_group = due_slot.get("group_url") or (target_groups[slot_idx % len(target_groups)])
        # 輪替選擇商品（依 slot_index 輪流展示）
        prod = avail_products[slot_idx % len(avail_products)]

        # 收集今日已用過的文案變體，確保每次都不一樣
        prev_metrics = fb_analytics.load_fb_metrics(acc_id)
        recent_variants = [m.get("variant_text", "") for m in prev_metrics[-4:]]
        post_text = ai_engine.rewrite_fb_group_post(prod, target_group, slot_idx, recent_variants, cfg)

        # 解析本地商品圖片（若為 products/media/... 直接取本地路徑上傳）
        img_val = prod.get("image_url", "")
        local_img = os.path.join(BASE_DIR, img_val) if img_val and not img_val.startswith("http") else None
        if local_img and not os.path.exists(local_img):
            local_img = None

        try:
            posted_group_res = await facebook_playwright.post_to_facebook_group(
                target_group, post_text, media_path=local_img, session_file=session_file
            )
            if posted_group_res.get("success"):
                fb_analytics.mark_slot_completed(acc_id, slot_idx, "DONE")
                fb_analytics.record_fb_post_metric(acc_id, {
                    "product_id": prod.get("id"),
                    "group_url": target_group,
                    "permalink": posted_group_res.get("permalink", ""),
                    "variant_text": post_text,
                    "slot_index": slot_idx
                })
        except Exception as fe:
            print(f"⚠️ [FB 社團排程發文] 執行失敗: {fe}")

    # 2. 自動回覆粉專留言/私訊（Graph API）& 社團貼文留言（Playwright）
    page_res = reply_fb_page_comments_and_dms(acc_id, acc, products, cfg)
    group_cmt_count = await reply_fb_group_comments_playwright(acc_id, session_file, products, cfg)

    return {
        "success": True,
        "group_posted": bool(posted_group_res and posted_group_res.get("success")),
        "page_api_res": page_res,
        "group_comments_replied": group_cmt_count
    }
