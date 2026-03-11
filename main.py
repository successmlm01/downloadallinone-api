from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import re
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoRequest(BaseModel):
    url: str

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://app.ytdown.to/en15/",
    "Origin": "https://app.ytdown.to",
}

def extract_video_id(url: str) -> str:
    patterns = [
        r"(?:v=|youtu\.be/)([^&\n?#]+)",
        r"(?:shorts/)([^&\n?#]+)",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return ""

async def get_ytcontent_url(video_id: str, quality: str, client: httpx.AsyncClient) -> dict:
    # Construire l'URL ytcontent
    import time
    timestamp = int(time.time() * 1000)
    ytcontent_url = f"https://s13.ytcontent.com/v5/video/{video_id}/{timestamp}/{quality}"

    # Appel proxy.php pour initier la conversion
    res = await client.post(
        "https://app.ytdown.to/proxy.php",
        data={"url": ytcontent_url},
        headers=HEADERS,
        timeout=30,
    )
    data = res.json()
    api = data.get("api", {})

    # Poll jusqu'à completion (max 30s)
    for _ in range(15):
        if api.get("status") == "completed" and api.get("fileUrl", "Waiting...") != "Waiting...":
            return {
                "fileUrl": api.get("fileUrl", ""),
                "fileSize": api.get("fileSize", ""),
                "fileName": api.get("fileName", ""),
            }
        import asyncio
        await asyncio.sleep(2)
        res2 = await client.post(
            "https://app.ytdown.to/proxy.php",
            data={"url": ytcontent_url},
            headers=HEADERS,
            timeout=30,
        )
        api = res2.json().get("api", {})

    return {}

@app.get("/")
def health():
    return {"status": "ok", "service": "DownloadAllinOne API"}

@app.post("/info")
async def get_video_info(req: VideoRequest):
    try:
        video_id = extract_video_id(req.url)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL")

        async with httpx.AsyncClient(timeout=60) as client:
            # 1. Check cooldown
            await client.post(
                "https://app.ytdown.to/cooldown.php",
                data={"action": "check"},
                headers=HEADERS,
            )

            # 2. Get video info via oEmbed
            oembed = await client.get(
                f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            )
            oembed_data = oembed.json()

            # 3. Get download URLs pour chaque qualité
            qualities = ["1080p", "720p", "480p", "360p"]
            formats = []

            for quality in qualities:
                result = await get_ytcontent_url(video_id, quality, client)
                if result.get("fileUrl"):
                    formats.append({
                        "quality": quality,
                        "format": "MP4",
                        "size": result.get("fileSize"),
                        "hasVideo": True,
                        "hasAudio": True,
                        "url": result["fileUrl"],
                    })

            if not formats:
                raise HTTPException(status_code=400, detail="No formats available")

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
