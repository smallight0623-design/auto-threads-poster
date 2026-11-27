import os
import sys
import yt_dlp

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def fetch_top_youtube_videos(query: str, min_views: int = 5000, limit: int = 10, max_duration_sec: int = 180) -> list:
    """
    透過 yt-dlp 免登入採集 YouTube 近期熱門短片 / Shorts 精華，
    篩選觀看數達標且片長 <= max_duration_sec 秒的影片以利 Threads 上傳。
    """
    search_queries = [f"ytsearch{limit + 6}:{query} shorts", f"ytsearch{limit}:{query}"]
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "ignoreerrors": True,
    }

    seen_ids = set()
    posts = []

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for sq in search_queries:
            try:
                info = ydl.extract_info(sq, download=False)
            except Exception as e:
                print(f"⚠️ [YouTube Scraper] 搜尋警告 ({sq}): {e}")
                continue

            entries = (info or {}).get("entries") or []
            for entry in entries:
                if not entry:
                    continue
                vid = entry.get("id")
                if not vid or vid in seen_ids:
                    continue

                views = int(entry.get("view_count") or 0)
                duration = int(entry.get("duration") or 0)

                if views < min_views:
                    continue
                # Threads 上傳影片建議控制在 3 分鐘內以兼顧轉碼速度與吸睛度
                if duration <= 0 or duration > max_duration_sec:
                    continue

                title = (entry.get("title") or "").strip()
                if not title:
                    continue

                seen_ids.add(vid)
                video_url = entry.get("url") or f"https://www.youtube.com/watch?v={vid}"
                if not video_url.startswith("http"):
                    video_url = f"https://www.youtube.com/watch?v={vid}"

                desc = (entry.get("description") or "").strip()
                full_content = f"{title}\n\n{desc[:400]}".strip() if desc else title

                posts.append({
                    "id": f"yt_{vid}",
                    "title": title,
                    "full_content": full_content,
                    "upvotes": views,
                    "replies_count": 0,
                    "media_type": "VIDEO",
                    "media_url": video_url,
                    "permalink": video_url,
                    "source_platform": "YouTube"
                })
                if len(posts) >= limit:
                    break
            if len(posts) >= limit:
                break

    posts.sort(key=lambda x: x["upvotes"], reverse=True)
    print(f"✅ [YouTube Scraper] 成功採集 {len(posts)} 支符合門檻 (≥{min_views} 觀看, ≤{max_duration_sec}秒) 之影片！")
    return posts[:limit]


if __name__ == "__main__":
    items = fetch_top_youtube_videos("Monster Hunter Wilds", min_views=1000, limit=5)
    for it in items:
        print(f"- [{it['id']}] ({it['upvotes']} views) {it['title'][:50]} -> {it['media_url']}")
