import sys
import re
import html
import urllib.request
import urllib.parse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 常見熱門遊戲巴哈姆特哈啦板 (BSN) 對照字典
COMMON_BAHA_BSN = {
    "monster hunter": "5786",
    "monsterhunter": "5786",
    "魔物獵人": "5786",
    "荒野": "5786",
    "原神": "36730",
    "genshin": "36730",
    "星穹鐵道": "72822",
    "崩壞：星穹鐵道": "72822",
    "star rail": "72822",
    "絕區零": "74860",
    "zzz": "74860",
    "鳴潮": "74934",
    "wuthering waves": "74934",
    "英雄聯盟": "17532",
    "lol": "17532",
    "寶可夢": "1647",
    "pokemon": "1647",
    "steam": "60599",
    "手機遊戲": "23805"
}

def resolve_bsn(query: str) -> str:
    """解析遊戲名稱或板塊代號為巴哈姆特 BSN"""
    q_clean = query.strip().lower()
    if q_clean.isdigit():
        return q_clean
    for k, bsn in COMMON_BAHA_BSN.items():
        if k in q_clean or q_clean in k:
            return bsn
    return "5786" # 預設魔物獵人

async def fetch_top_bahamut_posts(board_or_keyword: str, min_gp: int = 30, limit: int = 15):
    """
    採集台灣最大遊戲社群【巴哈姆特哈啦板】熱門爆文 (GP ≥ min_gp)。
    優勢：台灣玩家第一手真實討論、在地迷因、無 Cloudflare 防爬蟲阻擋、秒級高速擷取。
    """
    bsn = resolve_bsn(board_or_keyword)
    list_url = f"https://forum.gamer.com.tw/B.php?bsn={bsn}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://forum.gamer.com.tw/"
    }

    try:
        req = urllib.request.Request(list_url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            list_html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        raise Exception(f"無法載入巴哈姆特哈啦板 (BSN: {bsn}): {str(e)}")

    # 解析文章列表列 (b-list__row)
    rows = re.findall(r'<tr class="b-list__row[^"]*"[^>]*>(.*?)</tr>', list_html, re.DOTALL)
    candidates = []

    for r in rows:
        # 嚴格過濾置頂集中串（累積數年置頂串動輒數萬GP，並非單日即時爆文）
        if 'title="置頂"' in r or 'b-mark--update' in r or 'class="b-list__summary__mark' in r:
            continue

        gp_m = re.search(r'class="b-list__summary__gp[^"]*"[^>]*>(\d+)</span>', r)
        gp = int(gp_m.group(1)) if gp_m else 0
        if gp < min_gp:
            continue

        main_td = re.search(r'<td class="b-list__main"[^>]*>(.*?)</td>', r, re.DOTALL)
        if not main_td:
            continue
        content = main_td.group(1)

        # 優先從 b-list__main 提取真實文章標題與連結
        href_m = re.search(r'href="(C\.php\?bsn=\d+&[^"]+)"', content)
        title_m = re.search(r'class="b-list__main__title"[^>]*>(.*?)</(?:p|a)>', content, re.DOTALL)
        if not title_m:
            title_m = re.search(r'<a[^>]+href="C\.php\?[^"]+"[^>]*>(.*?)</a>', content, re.DOTALL)

        if not href_m or not title_m:
            continue

        raw_title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
        raw_title = html.unescape(raw_title)
        detail_href = "https://forum.gamer.com.tw/" + href_m.group(1)
        
        # 提取文章編號與回覆總數 (tnum)
        snA_m = re.search(r'snA=(\d+)', detail_href)
        tnum_m = re.search(r'tnum=(\d+)', detail_href)
        replies_count = int(tnum_m.group(1)) if tnum_m else 0
        article_id = f"baha_{bsn}_{snA_m.group(1)}" if snA_m else f"baha_{len(candidates)}"

        candidates.append({
            "id": article_id,
            "title": raw_title,
            "url": detail_href,
            "gp": gp,
            "replies_count": replies_count
        })
        if len(candidates) >= limit:
            break

    # 抓取內文詳細資料
    posts = []
    for item in candidates:
        try:
            d_req = urllib.request.Request(item["url"], headers=headers)
            with urllib.request.urlopen(d_req, timeout=8) as d_resp:
                detail_html = d_resp.read().decode("utf-8", errors="ignore")

            # 提取正文內容區塊 (容許巢狀 div 結構，直到作者操作列、簽名檔或回覆區)
            body_m = re.search(r'class="c-article__content[^"]*"[^>]*>(.*?)(?:<div class="c-article__actions|<div class="c-post__signature|<div class="c-reply)', detail_html, re.DOTALL)
            if not body_m:
                body_m = re.search(r'<div class="c-article__content[^"]*"[^>]*>(.*?)</div>', detail_html, re.DOTALL)
            if not body_m:
                continue

            content_html = body_m.group(1)

            # 提取圖片 (data-src 或 src)
            all_imgs = re.findall(r'<img[^>]+(?:data-src|src)="([^"]+)"', content_html)
            valid_imgs = [img for img in all_imgs if not img.endswith('.gif') and 'emotion' not in img and 'banner' not in img]
            media_type = "TEXT"
            media_url = None
            if valid_imgs:
                img_url = valid_imgs[0]
                if not img_url.startswith("http"):
                    img_url = "https:" + img_url if img_url.startswith("//") else ("https://forum.gamer.com.tw/" + img_url)
                media_type = "IMAGE"
                media_url = img_url

            # 清理 HTML 標籤
            clean_text = re.sub(r'<br\s*/?>', '\n', content_html)
            clean_text = re.sub(r'<[^>]+>', '', clean_text)
            clean_text = html.unescape(clean_text).strip()

            full_content = f"{item['title']}\n\n{clean_text}".strip()

            posts.append({
                "id": item["id"],
                "title": item["title"],
                "full_content": full_content,
                "upvotes": item["gp"],
                "replies_count": item.get("replies_count", 0),
                "media_type": media_type,
                "media_url": media_url,
                "image_count": len(valid_imgs),
                "permalink": item["url"],
                "source_platform": "巴哈姆特"
            })
        except Exception:
            continue

    return posts
