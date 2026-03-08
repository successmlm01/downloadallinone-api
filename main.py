from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import yt_dlp
import tempfile
import os

app = FastAPI()

class VideoRequest(BaseModel):
    url: str

@app.get("/")
def health():
    return {"status": "ok", "service": "DownloadAllinOne API"}

@app.post("/info")
def get_video_info(req: VideoRequest):
    
    # Écrire les cookies dans un fichier temporaire si disponible
    cookies_file = None
    cookies_content = os.environ.get("YOUTUBE_COOKIES", "")
    
    if cookies_content:
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        tmp.write(cookies_content)
        tmp.close()
        cookies_file = tmp.name

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
    }
    
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            formats = []
            seen = set()

            for f in info.get("formats", []):
                quality = f.get("format_note") or f.get("height") or "unknown"
                label = f"{quality}p" if isinstance(quality, int) else str(quality)
                ext = f.get("ext", "mp4")
                has_video = f.get("vcodec", "none") != "none"
                has_audio = f.get("acodec", "none") != "none"
                url = f.get("url", "")
                filesize = f.get("filesize") or f.get("filesize_approx")
                key = f"{label}-{ext}"
                if key in seen or not url:
                    continue
                seen.add(key)
                formats.append({
                    "quality": label,
                    "format": ext.upper(),
                    "size": f"~{round(filesize/1024/1024)}MB" if filesize else None,
                    "hasVideo": has_video,
                    "hasAudio": has_audio,
                    "url": url,
                })

            formats = sorted(
                formats,
                key=lambda x: (x["hasVideo"], x["hasAudio"]),
                reverse=True
            )[:6]

            thumbnail = info.get("thumbnail", "")
            if not thumbnail and "youtube" in req.url:
                vid_id = info.get("id", "")
                thumbnail = f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"

            return {
                "success": True,
                "title": info.get("title", "Video"),
                "thumbnail": thumbnail,
                "duration": str(info.get("duration_string", "N/A")),
                "author": info.get("uploader") or info.get("channel", "Unknown"),
                "formats": formats,
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if cookies_file and os.path.exists(cookies_file):
            os.unlink(cookies_file)
