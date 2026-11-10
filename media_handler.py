import os
import requests
import yt_dlp

def download_media(media_type: str, media_url: str, post_id: str) -> str:
    """
    下載圖片或影片至本地 downloads 資料夾，回傳本地檔案絕對路徑。
    Playwright 即可直接 set_input_files 上傳，無須另外託管圖床。
    """
    if not media_url:
        return None

    downloads_dir = os.path.abspath("downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    if media_type == "IMAGE":
        # 排除非直連圖檔網址 (如 /gallery/)
        if "/gallery/" in media_url or not media_url.startswith("http"):
            print(f"⚠️ 跳過無效圖片連結: {media_url}")
            return None

        ext = "jpg"
        clean_url = media_url.split("?")[0]
        if "." in clean_url:
            candidate_ext = clean_url.split(".")[-1].lower()
            if candidate_ext in ["jpg", "jpeg", "png", "webp"]:
                ext = candidate_ext

        file_path = os.path.join(downloads_dir, f"{post_id}.{ext}")
        headers = {"User-Agent": "Mozilla/5.0"}
        
        try:
            res = requests.get(media_url, headers=headers, timeout=25)
            res.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(res.content)
            return file_path
        except Exception as e:
            print(f"⚠️ 圖片下載失敗 ({media_url}): {str(e)}，將改以純文字發布")
            return None

    elif media_type == "VIDEO":
        output_template = os.path.join(downloads_dir, f"{post_id}.%(ext)s")
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': output_template,
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([media_url])
        except Exception as e:
            print(f"⚠️ 影片下載/壓制失敗 ({media_url}): {str(e)}，將改以純文字發布")
            return None

        final_path = os.path.join(downloads_dir, f"{post_id}.mp4")
        if os.path.exists(final_path):
            return final_path

    return None
