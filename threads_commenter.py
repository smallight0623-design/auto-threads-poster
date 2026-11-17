import os
import sys
import json
import time
import urllib.parse
import datetime
import random
import asyncio
from playwright.async_api import async_playwright

import account_manager
import ai_engine

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_comment_history_path(acc_id: str) -> str:
    acc_dir = os.path.join(BASE_DIR, "accounts", acc_id)
    os.makedirs(acc_dir, exist_ok=True)
    return os.path.join(acc_dir, "comment_history.json")

def load_comment_history(acc_id: str) -> list:
    fpath = get_comment_history_path(acc_id)
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_comment_history(acc_id: str, history: list):
    fpath = get_comment_history_path(acc_id)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def log_comment_action(acc_id: str, entry: dict):
    history = load_comment_history(acc_id)
    entry["id"] = f"cmt_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(100, 999)}"
    entry["created_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history.append(entry)
    save_comment_history(acc_id, history)

def get_today_comment_count(acc_id: str) -> int:
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    history = load_comment_history(acc_id)
    count = 0
    for item in history:
        if item.get("created_at", "").startswith(today_str) and item.get("status") == "success":
            count += 1
    return count

async def search_hot_threads(page, keyword: str, limit: int = 6) -> list:
    """
    透過 Threads 官方搜尋雷達掃描指定關鍵字的即時熱門話題
    """
    encoded_kw = urllib.parse.quote(keyword)
    search_url = f"https://www.threads.net/search?q={encoded_kw}&serp_type=default"
    print(f"🔍 [Threads 海巡] 正在搜尋關鍵字「{keyword}」: {search_url}")
    
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(3500)
    except Exception as e:
        print(f"⚠️ [Threads 海巡] 搜尋頁面載入警告: {e}")
        await page.wait_for_timeout(2000)

    # 抓取頁面所有結構化貼文資訊
    posts_data = await page.evaluate(r'''() => {
        const results = [];
        const seenUrls = new Set();
        
        // 抓取所有貼文容器
        const containers = Array.from(document.querySelectorAll('div[data-pressable-container="true"], article, div[role="article"]'));
        for (const c of containers) {
            const link = c.querySelector('a[href*="/post/"]');
            if (!link) continue;
            
            // 清理網址，排除 /media 等尾綴
            let href = link.href;
            const match = href.match(/(https:\/\/(www\.)?threads\.(net|com)\/@[^\/]+\/post\/[a-zA-Z0-9_\-]+)/);
            if (!match) continue;
            const cleanUrl = match[1].replace('threads.com', 'threads.net');
            
            if (seenUrls.has(cleanUrl)) continue;
            seenUrls.add(cleanUrl);

            // 提取作者
            const authorMatch = cleanUrl.match(/@([^\/]+)/);
            const author = authorMatch ? authorMatch[1] : "";

            // 提取內文
            const text = (c.innerText || "").replace(/\\s+/g, ' ').trim();

            results.push({
                url: cleanUrl,
                author: author,
                text: text.slice(0, 300)
            });
        }
        return results;
    }''')
    
    print(f"📊 [Threads 海巡] 關鍵字「{keyword}」探索到 {len(posts_data)} 則有效貼文")
    return posts_data[:limit]

async def post_thread_reply(page, post_url: str, reply_text: str) -> dict:
    """
    深入目標貼文頁面，模擬真人玩家進行神回覆發布
    """
    print(f"🎯 [Threads 留言] 前往目標貼文: {post_url}")
    try:
        try:
            await page.goto(post_url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(3000)
        except Exception as e:
            return {"success": False, "error": f"載入貼文頁面逾時: {str(e)}"}

        # 1. 檢測輸入框是否已經出現在畫面上 (例如底部已有輸入列)
        textbox = page.locator('div[role="textbox"]').first
        is_tb_ready = False
        try:
            is_tb_ready = await textbox.is_visible()
        except Exception:
            pass

        if not is_tb_ready:
            # 尋找並點擊回覆對話框觸發器 ("Reply to ...")
            reply_trigger = page.locator("text='Reply to'").or_(page.locator("div:has-text('Reply to')")).first
            has_trigger = False
            try:
                has_trigger = await reply_trigger.is_visible()
            except Exception:
                pass

            if has_trigger:
                try:
                    await reply_trigger.click(force=True, timeout=4000)
                except Exception:
                    await page.evaluate(r'''() => {
                        const all = Array.from(document.querySelectorAll('*'));
                        for (const el of all) {
                            if (el.innerText && el.innerText.startsWith('Reply to') && el.children.length === 0) {
                                el.click();
                                return;
                            }
                        }
                    }''')
                await page.wait_for_timeout(1500)
            else:
                # 嘗試找尋留言泡泡圖示
                bubble = page.locator('div[role="button"]:has(svg[aria-label*="Reply" i]), div[role="button"]:has(svg[aria-label*="回覆" i])').first
                try:
                    if await bubble.is_visible():
                        await bubble.click(force=True, timeout=4000)
                        await page.wait_for_timeout(1500)
                except Exception:
                    pass

        # 2. 定位輸入框 (role="textbox")
        textbox = page.locator('div[role="textbox"]').first
        try:
            await textbox.wait_for(state="visible", timeout=6000)
        except Exception:
            pass

        if not await textbox.is_visible():
            return {"success": False, "error": "輸入框未如期顯現"}

        # 聚焦與輸入文字 (使用短超時與 force=True，徹底杜絕 30s 鎖死)
        try:
            await textbox.click(force=True, timeout=3000)
        except Exception:
            try:
                await textbox.focus(timeout=2000)
            except Exception:
                pass

        filled = False
        try:
            await textbox.fill(reply_text, timeout=4000)
            filled = True
        except Exception:
            pass

        if not filled:
            # Fallback: 使用 JS 聚焦並填入
            await page.evaluate(r'''({ text }) => {
                const tb = document.querySelector('div[role="textbox"]');
                if (tb) {
                    tb.focus();
                    document.execCommand('selectAll', false, null);
                    document.execCommand('insertText', false, text);
                    tb.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }''', {"text": reply_text})

        await page.wait_for_timeout(1000)

        # 3. 點擊發布按鈕 (相容旋轉箭頭按鈕與 Post / 發布 / 回覆 文字按鈕)
        clicked = await page.evaluate(r'''() => {
            const tb = document.querySelector('div[role="textbox"]');
            if (tb) {
                let parent = tb;
                for (let i = 0; i < 6; i++) {
                    if (parent.parentElement) parent = parent.parentElement;
                }
                const btns = Array.from(parent.querySelectorAll('div[role="button"], button'));
                for (const b of btns) {
                    const txt = (b.innerText || '').trim();
                    if (txt === 'Post' || txt === '發布' || txt === '回覆' || b.innerHTML.includes('rotate(90deg)')) {
                        b.click();
                        return true;
                    }
                }
                if (btns.length > 0) {
                    btns[btns.length - 1].click();
                    return true;
                }
            }
            // 全域搜尋 Post 按鈕
            const allBtns = Array.from(document.querySelectorAll('div[role="button"], button'));
            for (const b of allBtns) {
                const txt = (b.innerText || '').trim();
                if (txt === 'Post' || txt === '發布') {
                    b.click();
                    return true;
                }
            }
            return false;
        }''')

        if not clicked:
            return {"success": False, "error": "未能觸發發布按鈕"}

        print("🚀 [Threads 留言] 已點擊發送按鈕，等待系統回應...")
        await page.wait_for_timeout(4000)

        # 4. 驗證是否出現 Posted / 已發布 提示訊息
        is_posted = False
        try:
            is_posted = await page.locator("text='Posted'").or_(page.locator("text='已發布'")).is_visible()
        except Exception:
            pass
        
        # 備選驗證：輸入框是否已消失或被重置
        tb_text = await page.evaluate(r'''() => {
            const tb = document.querySelector('div[role="textbox"]');
            return tb ? tb.innerText.trim() : "";
        }''')

        if is_posted or not tb_text:
            print(f"✅ [Threads 留言] 成功發布神回覆: {reply_text}")
            return {"success": True, "error": None}
        else:
            return {"success": True, "error": None, "note": "已送出但未捕獲明確 Toast"}

    except Exception as e:
        print(f"❌ [Threads 留言異常] {e}")
        return {"success": False, "error": str(e)}

async def run_threads_patrol_async(acc_id: str, max_comments: int = 2) -> dict:
    """
    執行單次 Threads 留言海巡週期：
    1. 檢查今日配額與安全頻率
    2. 依據關鍵字探索目標貼文
    3. 過濾自身貼文與已回覆歷史
    4. 調用 AI 產生真誠玩家神回覆並留言
    5. 紀錄反哺情報
    """
    acc = account_manager.get_account(acc_id)
    if not acc:
        return {"success": False, "error": f"找不到帳號 {acc_id}"}
    
    target_platform = acc.get("target_platform", "Threads")
    if target_platform != "Threads":
        return {"success": False, "error": f"此帳號目標平台為 {target_platform}，海巡留言僅支援 Threads"}

    session_file = os.path.join(BASE_DIR, "accounts", acc_id, "session.json")
    if not os.path.exists(session_file):
        return {"success": False, "error": f"帳號尚未綁定有效 Session (找不到 {session_file})"}

    # 讀取海巡相關設定
    daily_limit = int(acc.get("comment_daily_limit") or 10)
    today_count = get_today_comment_count(acc_id)
    if today_count >= daily_limit:
        return {
            "success": False,
            "error": f"今日海巡留言數已達安全上限 ({today_count}/{daily_limit})，防封控機制自動休眠",
            "today_count": today_count
        }

    # 關鍵字清單
    keywords = acc.get("comment_keywords")
    if not keywords:
        game = acc.get("game_name", "")
        if "Monster Hunter" in game or "魔物" in game:
            keywords = ["魔物獵人", "MHWilds", "荒野"]
        elif "傳說對決" in game:
            keywords = ["傳說對決", "AOV"]
        else:
            keywords = [game] if game else ["遊戲"]

    # 隨機打亂以避免每次順序固定
    kw_pool = list(keywords)
    random.shuffle(kw_pool)

    # 載入已留言歷史以防重複洗版
    history = load_comment_history(acc_id)
    replied_urls = set(item.get("post_url", "").lower() for item in history)

    # 讀取自己帳號名稱（避免回覆自己）
    acc_name = acc.get("name", "")
    threads_username = ""
    if "@" in acc_name:
        threads_username = acc_name.split("@")[-1].split()[0].strip()
    elif "." in acc_name:
        parts = acc_name.split()
        threads_username = parts[0].strip()

    persona = account_manager.get_account_persona(acc_id)
    global_cfg = account_manager.get_global_settings()
    game_name = acc.get("game_name", "遊戲")

    results = []
    commented_this_run = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=session_file,
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        try:
            for kw in kw_pool:
                if commented_this_run >= max_comments:
                    break

                candidates = await search_hot_threads(page, kw, limit=6)
                for post in candidates:
                    if commented_this_run >= max_comments:
                        break

                    p_url = post["url"]
                    p_author = post["author"]
                    p_text = post["text"]

                    # 安全過濾：跳過自身、跳過已留言、跳過無意義短文
                    if threads_username and threads_username.lower() in p_author.lower():
                        continue
                    if p_url.lower() in replied_urls:
                        continue
                    if len(p_text) < 5:
                        continue

                    print(f"\n💡 [海巡選題選中] @{p_author}: {p_text[:60]}...")
                    
                    # 1. 意圖評估器 (借鑑 kaymen99/sales-outreach 意圖狀態機)
                    import social_seller
                    intent_res = social_seller.evaluate_lead_intent(p_text, game_name, global_cfg)
                    is_lead = intent_res.get("should_reply", False)
                    intent_score = intent_res.get("intent_score", 3)
                    pain_point = intent_res.get("pain_point", "")

                    if is_lead:
                        print(f"🎯 [精準潛在客戶] 命中痛點 ({intent_score}分): {pain_point}")
                        # 2. 變色龍隱形推銷生成器 (借鑑 AICMO 80/20 黃金推銷提示詞)
                        target_reply = social_seller.generate_stealth_chameleon_reply(
                            post_text=p_text,
                            author=p_author,
                            pain_point=pain_point,
                            game_name=game_name,
                            config=global_cfg
                        )
                        print(f"🥷 [變色龍隱形推銷回覆]: {target_reply}")
                    else:
                        # 普通日常互動：載入實戰金句庫生成神回覆 (V2 靈動版)
                        import threads_learner
                        kb = threads_learner.load_knowledge_base(acc_id)
                        golden_quotes = kb.get("golden_comments", [])
                        target_reply = ai_engine.generate_witty_comment(
                            post_text=p_text,
                            author=p_author,
                            game_name=game_name,
                            persona=persona,
                            config=global_cfg,
                            golden_quotes=golden_quotes
                        )
                        print(f"💬 [日常高情商神回覆]: {target_reply}")

                    # 3. 執行發布
                    post_res = await post_thread_reply(page, p_url, target_reply)
                    
                    log_entry = {
                        "post_url": p_url,
                        "author": p_author,
                        "keyword": kw,
                        "post_snippet": p_text[:120],
                        "comment_text": target_reply,
                        "is_sales_lead": is_lead,
                        "intent_score": intent_score,
                        "pain_point": pain_point,
                        "status": "success" if post_res["success"] else "failed",
                        "error": post_res.get("error")
                    }
                    log_comment_action(acc_id, log_entry)
                    if is_lead and post_res["success"]:
                        social_seller.log_sales_lead(acc_id, log_entry)
                    replied_urls.add(p_url.lower())

                    if post_res["success"]:
                        commented_this_run += 1
                        results.append(log_entry)
                        print(f"🎉 [海巡成功] 本次已留言 {commented_this_run}/{max_comments}")

                        # 兩則留言間的安全間隔 (12 ~ 20 秒)
                        if commented_this_run < max_comments:
                            sleep_sec = random.randint(12, 20)
                            print(f"⏳ 安全擬真等待 {sleep_sec} 秒後繼續下一次巡邏...")
                            await asyncio.sleep(sleep_sec)
                    else:
                        print(f"⚠️ [海巡跳過] 貼文留言未成功 ({post_res.get('error')})，繼續搜尋下一則候選貼文...")

        finally:
            await browser.close()

    # 更新帳號最後留言時間
    if commented_this_run > 0:
        data = account_manager.load_data()
        for a in data.get("accounts", []):
            if a["id"] == acc_id:
                a["last_comment_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break
        account_manager.save_data(data)

    return {
        "success": True,
        "commented_count": commented_this_run,
        "results": results,
        "today_total": today_count + commented_this_run
    }

def run_threads_patrol(acc_id: str, max_comments: int = 2) -> dict:
    """同步包裝函數供外部 API 或排程呼叫"""
    return asyncio.run(run_threads_patrol_async(acc_id, max_comments))

if __name__ == '__main__':
    # 測試執行單次海巡 (限制 1 則測試)
    res = run_threads_patrol("acc_primary", max_comments=1)
    print("\n執行結果:", json.dumps(res, ensure_ascii=False, indent=2))
