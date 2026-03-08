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
    cookies_file = None
    cookies_content = os.environ.get("YOUTUBE_COOKIES", "")

    if cookies_content:
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        tmp.write(cookies_content)
        tmp.close()
        cookies_file = tmp.name

    ydl_opts = {"quiet": True, "no_warnings": True}
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)

            # Formats combinés vidéo+audio (prêts à lire)
            combined = []
            for f in info.get("formats", []):
                has_video = f.get("vcodec", "none") != "none"
                has_audio = f.get("acodec", "none") != "none"
                url = f.get("url", "")
                height = f.get("height")
                ext = f.get("ext", "mp4")
                filesize = f.get("filesize") or f.get("filesize_approx")

                # Garder seulement les formats avec vidéo ET audio
                if has_video and has_audio and url and height:
                    combined.append({
                        "quality": f"{height}p",
                        "format": ext.upper(),
                        "size": f"~{round(filesize/1024/1024)}MB" if filesize else None,
                        "hasVideo": True,
                        "hasAudio": True,
                        "url": url,
                        "height": height,
                    })

            # Trier par qualité décroissante et dédupliquer
            seen = set()
            formats = []
            for f in sorted(combined, key=lambda x: x["height"], reverse=True):
                key = f["quality"]
                if key not in seen:
                    seen.add(key)
                    formats.append({k: v for k, v in f.items() if k != "height"})

            # Ajouter audio MP3 séparé
            for f in info.get("formats", []):
                if f.get("acodec", "none") != "none" and f.get("vcodec", "none") == "none":
                    formats.append({
                        "quality": "Audio MP3",
                        "format": "MP3",
                        "size": None,
                        "hasVideo": False,
                        "hasAudio": True,
                        "url": f.get("url", ""),
                    })
                    break

            # Limiter à 6 formats
            formats = formats[:6]

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
