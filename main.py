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

            # Priorité 1 : formats vidéo+audio combinés
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

            # Priorité 2 : vidéo-only pour les résolutions manquantes
            target_heights = [1080, 720, 480, 360, 240]
            for target in target_heights:
                if target in seen_heights:
                    continue
                best = None
                for f in all_formats:
                    has_video = f.get("vcodec", "none") != "none"
                    height = f.get("height")
                    url = f.get("url", "")
                    ext = f.get("ext", "mp4")
                    if has_video and height == target and url and ext == "mp4":
                        filesize = f.get("filesize") or f.get("filesize_approx") or 0
                        if best is None or filesize > (best.get("filesize") or 0):
                            best = f
                if best:
                    filesize = best.get("filesize") or best.get("filesize_approx")
                    formats.append({
                        "quality": f"{target}p",
                        "format": "MP4",
                        "size": f"~{round(filesize/1024/1024)}MB" if filesize else None,
                        "hasVideo": True,
                        "hasAudio": False,
                        "url": best.get("url", ""),
                    })
                    seen_heights.add(target)

            # Trier par qualité décroissante
            def sort_key(f):
                try:
                    return int(f["quality"].replace("p", ""))
                except:
                    return 0

            formats = sorted(formats, key=sort_key, reverse=True)[:5]

            # Meilleur audio seul
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
