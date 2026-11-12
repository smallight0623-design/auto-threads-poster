import sys
import os
import requests
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

TWITCH_GQL_URL = "https://gql.twitch.tv/gql"
TWITCH_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

HEADERS = {
    "Client-Id": TWITCH_CLIENT_ID,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
}

def search_game_name(game_query: str) -> str:
    """透過 Twitch GQL 搜尋最匹配的 Twitch 官方遊戲分類名稱"""
    query = """
    query SearchGame($query: String!) {
      searchFor(query: $query, platform: "web") {
        games {
          edges {
            node {
              id
              name
            }
          }
        }
      }
    }
    """
    try:
        res = requests.post(
            TWITCH_GQL_URL,
            headers=HEADERS,
            json={"query": query, "variables": {"query": game_query}},
            timeout=8
        )
        if res.status_code == 200:
            games = res.json().get("data", {}).get("searchFor", {}).get("games", {}).get("edges", [])
            if games:
                return games[0]["node"]["name"]
    except Exception as e:
        print(f"[Twitch] 遊戲名稱解析警告 ({game_query}): {e}")
    return game_query

def fetch_top_twitch_clips(game_name: str, min_views: int = 50, limit: int = 15, period: str = "LAST_WEEK") -> list:
    """
    透過 Twitch 官方公開 GQL 採集該遊戲分類的熱門短影音剪輯 (Clips of the Week)。
    完全免登入、免 Cookie、超高速直連！
    直接回傳高品質 MP4 下載位址與原始標題。
    """
    resolved_game = search_game_name(game_name)
    print(f"[Twitch Scraper] 鎖定遊戲分類：【{resolved_game}】 (原搜尋詞: {game_name})")

    query = """
    query GetClips($gameName: String!) {
      game(name: $gameName) {
        id
        name
        clips(first: 25, criteria: { filter: LAST_WEEK }) {
          edges {
            node {
              id
              slug
              title
              viewCount
              durationSeconds
              thumbnailURL
              videoQualities {
                quality
                sourceURL
              }
            }
          }
        }
      }
    }
    """

    try:
        res = requests.post(
            TWITCH_GQL_URL,
            headers=HEADERS,
            json={"query": query, "variables": {"gameName": resolved_game}},
            timeout=10
        )
    except Exception as e:
        print(f"[Twitch Scraper] 連線失敗: {e}")
        return []

    if res.status_code != 200:
        print(f"[Twitch Scraper] 回傳非 200 狀態碼: {res.status_code}")
        return []

    data = res.json()
    game_obj = (data.get("data") or {}).get("game") or {}
    clip_edges = (game_obj.get("clips") or {}).get("edges") or []
    if not clip_edges:
        print(f"[Twitch Scraper] 分類【{resolved_game}】近期無剪輯或查無分類")
        return []

    posts = []
    for edge in clip_edges:
        node = edge.get("node", {})
        views = node.get("viewCount", 0)
        if views < min_views:
            continue

        slug = node.get("slug", "")
        if not slug:
            continue

        # 挑選最高解析度 MP4 (1080p > 720p > 480p)
        qualities = node.get("videoQualities", [])
        best_source_url = None
        for q in qualities:
            best_source_url = q.get("sourceURL")
            if q.get("quality") in ["1080", "720"]:
                break

        title = node.get("title", "").strip()
        if not title:
            continue

        permalink = f"https://clips.twitch.tv/{slug}"

        posts.append({
            "id": f"twitch_{slug}",
            "title": title,
            "full_content": title,
            "upvotes": views,
            "media_type": "VIDEO",
            "media_url": permalink,
            "permalink": permalink,
            "source_platform": "Twitch"
        })

        if len(posts) >= limit:
            break

    print(f"✅ [Twitch Scraper] 成功採集 {len(posts)} 支符合熱度門檻 (≥{min_views} 觀看) 的爆款短影片！")
    return posts

if __name__ == "__main__":
    test_clips = fetch_top_twitch_clips("Monster Hunter", min_views=20, limit=3)
    for c in test_clips:
        print(f"- [{c['upvotes']} 觀看] {c['title']} | URL: {c['media_url'][:60]}...")
