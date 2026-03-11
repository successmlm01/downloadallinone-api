from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import re
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoRequest(BaseModel):
    url: str

def extract_video_id(url: str) -> str:
    patterns = [r"(?:v=|youtu\.be/)([^&\n?#]+)", r"(?:shorts/)([^&\n?#]+)"]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return ""

@app.get("/")
def health():
    return {"status": "ok", "service": "DownloadAllinOne API"}

@app.post("/info")
async def get_video_info(req: VideoRequest):
    try:
        video_id = extract_video_id(req.url)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL")

        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            # Get video metadata
            oembed = await client.get(
                f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            )
            oembed_data = oembed.json()

            # Appel direct à ytcontent.com
            qualities = [
                ("1080p", "1080p"),
                ("720p", "720p"),
                ("480p", "480p"),
                ("360p", "360p"),
                ("mp3", "Audio MP3"),
            ]

            formats = []
            ts = int(time.time() * 1000)

            for quality_key, quality_label in qualities:
                try:
                    url_ytcontent = f"https://s13.ytcontent.com/v5/video/{video_id}/{ts}/{quality_key}"
                    
                    # Initier la conversion
                    res = await client.post(
                        "https://s13.ytcontent.com/v5/convert",
                        data={"url": url_ytcontent},
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Referer": "https://s13.ytcontent.com/",
                            "Origin": "https://s13.ytcontent.com",
                        },
                        timeout=20,
                    )

                    if res.status_code == 200:
                        data = res.json()
                        file_url = data.get("fileUrl") or data.get("url") or data.get("download_url")
                        if file_url and file_url != "Waiting...":
                            formats.append({
                                "quality": quality_label,
                                "format": "MP3" if quality_key == "mp3" else "MP4",
                                "size": data.get("fileSize"),
                                "hasVideo": quality_key != "mp3",
                                "hasAudio": True,
                                "url": file_url,
                            })
                except Exception:
                    continue

            # Fallback si ytcontent ne fonctionne pas
            if not formats:
                formats = [
                    {"quality": "1080p", "format": "MP4", "size": None, "hasVideo": True, "hasAudio": True,
                     "url": f"https://s13.ytcontent.com/v5/download/{video_id}/{ts}/1080p"},
                    {"quality": "720p", "format": "MP4", "size": None, "hasVideo": True, "hasAudio": True,
                     "url": f"https://s13.ytcontent.com/v5/download/{video_id}/{ts}/720p"},
                    {"quality": "480p", "format": "MP4", "size": None, "hasVideo": True, "hasAudio": True,
                     "url": f"https://s13.ytcontent.com/v5/download/{video_id}/{ts}/480p"},
                    {"quality": "360p", "format": "MP4", "size": None, "hasVideo": True, "hasAudio": True,
                     "url": f"https://s13.ytcontent.com/v5/download/{video_id}/{ts}/360p"},
                    {"quality": "Audio MP3", "format": "MP3", "size": None, "hasVideo": False, "hasAudio": True,
                     "url": f"https://s13.ytcontent.com/v5/download/{video_id}/{ts}/mp3"},
                ]

            return {
                "success": True,
                "title": oembed_data.get("title", "Video"),
                "thumbnail": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                "duration": "N/A",
                "author": oembed_data.get("author_name", "YouTube"),
                "formats": formats,
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
