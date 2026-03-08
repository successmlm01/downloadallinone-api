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

    # On extrait juste les infos sans forcer un format spécifique
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)

            all_formats = info.get("formats", [])
            formats = []
            seen_heights = set()

            # 1. Formats vidéo avec audio intégré (rare sur YouTube mais possible)
            for f in sorted(all_formats, key=lambda x: x.get("height") or 0, reverse=True):
                has_video = f.get("vcodec", "none") != "none"
                has_audio = f.get("acodec", "none") != "none"
                height = f.get("height")
                url = f.get("url", "")
                ext = f.get("ext", "mp4")
                filesize = f.get("filesize") or f.get("filesize_approx")

                if has_video and has_audio and url and height and height not in seen_heights:
                    seen_heights.add(height)
                    formats.append({
                        "quality": f"{height}p",
                        "format": ext.upper(),
                        "size": f"~{round(filesize/1024/1024)}MB" if filesize else None,
                        "hasVideo": True,
                        "hasAudio": True,
                        "url": url,
                    })

            # 2. Si pas assez de formats combinés, ajouter les vidéo-only
            #    (le navigateur peut les lire directement via <video>)
            seen_heights_vo = set()
            for f in sorted(all_formats, key=lambda x: x.get("height") or 0, reverse=True):
                has_video = f.get("vcodec", "none") != "none"
                has_audio = f.get("acodec", "none") != "none"
                height = f.get("height")
                url = f.get("url", "")
                ext = f.get("ext", "mp4")
                filesize = f.get("filesize") or f.get("filesize_approx")

                if has_video and not has_audio and url and height and height not in seen_heights and height not in seen_heights_vo:
                    seen_heights_vo.add(height)
                    formats.append({
                        "quality": f"{height}p",
                        "format": ext.upper(),
                        "size": f"~{round(filesize/1024/1024)}MB" if filesize else None,
                        "hasVideo": True,
                        "hasAudio": False,
                        "url": url,
                    })

                if len(formats) >= 5:
                    break

            # 3. Meilleur audio seul
            best_audio = None
            best_abr = 0
            for f in all_formats:
                has_video = f.get("vcodec", "none") != "none"
                has_audio = f.get("acodec", "none") != "none"
                abr = f.get("abr") or 0
                if has_audio and not has_video and abr > best_abr:
                    best_abr = abr
                    best_audio = f

            if best_audio:
                formats.append({
                    "quality": "Audio MP3",
                    "format": "MP3",
                    "size": None,
                    "hasVideo": False,
                    "hasAudio": True,
                    "url": best_audio.get("url", ""),
                })

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
