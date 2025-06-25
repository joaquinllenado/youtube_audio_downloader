from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import os
import uuid
import glob
from fastapi.responses import FileResponse
import logging
import asyncio
import time
import yt_dlp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="YouTube Audio Downloader", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Rate limiting
last_request_time = 0
MIN_REQUEST_INTERVAL = 2  # 2 seconds between requests

class YouTubeDownloadRequest(BaseModel):
    url: HttpUrl

async def cleanup_file(file_path: str):
    """Async function to clean up downloaded file"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up file {file_path}: {e}")

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {"status": "healthy", "service": "youtube-audio-downloader"}

@app.post("/download")
async def download_youtube_audio(request: YouTubeDownloadRequest):
    global last_request_time
    
    # Rate limiting
    current_time = time.time()
    time_since_last = current_time - last_request_time
    if time_since_last < MIN_REQUEST_INTERVAL:
        sleep_time = MIN_REQUEST_INTERVAL - time_since_last
        await asyncio.sleep(sleep_time)
    
    last_request_time = time.time()
    
    video_url = str(request.url)
    file_id = str(uuid.uuid4())
    output_template = f"{DOWNLOAD_DIR}/{file_id}.%(ext)s"

    logger.info(f"Starting download for URL: {video_url}")

    # Simple yt-dlp options
    options = {
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio',
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }

    try:
        # Use yt-dlp Python API
        with yt_dlp.YoutubeDL(options) as ydl:
            # Download the video
            ydl.download([video_url])

        # Find the generated file using glob pattern
        downloaded_files = glob.glob(f"{DOWNLOAD_DIR}/{file_id}.*")
        
        if not downloaded_files:
            raise HTTPException(status_code=500, detail="Audio file not found after download")
        
        file_path = downloaded_files[0]
        file_size = os.path.getsize(file_path)
        
        logger.info(f"Download completed: {file_path} ({file_size} bytes)")
        
        # Determine media type based on file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        media_types = {
            '.m4a': 'audio/mp4',
            '.webm': 'audio/webm',
            '.opus': 'audio/opus',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav'
        }
        media_type = media_types.get(file_ext, 'audio/mpeg')
        
        # Return the file and clean it up after serving
        return FileResponse(
            file_path, 
            media_type=media_type, 
            filename=os.path.basename(file_path),
            background=lambda: asyncio.create_task(cleanup_file(file_path))
        )
        
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"yt-dlp error for URL {video_url}: {error_msg}")
        
        # Check if it's an ffmpeg-related error
        if "ffmpeg" in error_msg.lower() or "ffprobe" in error_msg.lower():
            raise HTTPException(
                status_code=500, 
                detail="Audio conversion failed. Please install ffmpeg: https://ffmpeg.org/download.html"
            )
        
        # Check for bot detection errors
        if any(keyword in error_msg.lower() for keyword in ["bot", "429", "too many requests", "precondition check failed", "sign in to confirm"]):
            raise HTTPException(
                status_code=429,
                detail="YouTube is blocking automated requests. Please try again later or use a different video."
            )
        
        # Check for SSL errors
        if "ssl" in error_msg.lower() or "certificate" in error_msg.lower():
            raise HTTPException(
                status_code=500,
                detail="SSL certificate verification failed. Please try again later."
            )
        
        # Generic error
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to download audio: {error_msg}"
        )
        
    except Exception as e:
        logger.error(f"Unexpected error for URL {video_url}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Unexpected error: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)