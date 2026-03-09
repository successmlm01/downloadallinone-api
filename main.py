from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import yt_dlp, tempfile, os

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
        "extractor_args": {"youtube": {"player_client": ["tv_embedded", "ios"]}},
    }
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            all_formats = info.get("formats", [])

            # Debug: afficher tous les formats reçus
            print("=== FORMATS REÇUS ===")
            for f in all_formats:
                print(f"height={f.get('height')} ext={f.get('ext')} has_v={f.get('vcodec','none')!='none'} has_a={f.get('acodec','none')!='none'}")

            best_by_height = {}
            for f in all_formats:
                has_video = f.get("vcodec", "none") != "none"
                height = f.get("height")
                url = f.get("url", "")
                ext = f.get("ext", "mp4")
                if not has_video or not height or not url:
                    continue
                if ext not in ("mp4", "webm"):
                    continue
                has_audio = f.get("acodec", "none") != "none"
                if height not in best_by_height:
                    best_by_height[height] = f
                else:
                    prev = best_by_height[height]
                    prev_has_audio = prev.get("acodec", "none") != "none"
                    if not prev_has_audio and has_audio:
                        best_by_height[height] = f
                    elif ext == "mp4" and prev.get("ext") == "webm" and not (prev_has_audio and not has_audio):
                        best_by_height[height] = f

            labels = {2160:"4K",1440:"2K",1080:"1080p",720:"720p",480:"480p",360:"360p",240:"240p",144:"144p"}
            formats = []
            for height in sorted(best_by_height.keys(), reverse=True):
                f = best_by_height[height]
                has_audio = f.get("acodec", "none") != "none"
                ext = f.get("ext", "mp4")
                filesize = f.get("filesize") or f.get("filesize_approx")
                formats.append({
                    "quality": labels.get(height, f"{height}p"),
                    "format": ext.upper(),
                    "size": f"~{round(filesize/1024/1024)}MB" if filesize else None,
                    "hasVideo": True,
                    "hasAudio": has_audio,
                    "url": f.get("url", ""),
                })
                if len(formats) == 6:
                    break

            best_audio = None
            best_abr = 0
            for f in all_formats:
                if f.get("vcodec","none") == "none" and f.get("acodec","none") != "none":
                    abr = f.get("abr") or 0
                    if abr > best_abr:
                        best_abr = abr
                        best_audio = f
            if best_audio:
                formats.append({"quality":"Audio MP3","format":"MP3","size":None,"hasVideo":False,"hasAudio":True,"url":best_audio.get("url","")})

            thumbnail = info.get("thumbnail","")
            if not thumbnail and "youtube" in req.url:
                thumbnail = f"https://img.youtube.com/vi/{info.get('id','')}/maxresdefault.jpg"

            return {"success":True,"title":info.get("title","Video"),"thumbnail":thumbnail,"duration":str(info.get("duration_string","N/A")),"author":info.get("uploader") or info.get("channel","Unknown"),"formats":formats}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if cookies_file and os.path.exists(cookies_file):
            os.unlink(cookies_file)
