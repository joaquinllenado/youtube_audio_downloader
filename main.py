from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import os
import subprocess
import uuid
import glob
from fastapi.responses import FileResponse
import logging
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="YouTube Audio Downloader", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Configure this properly for production - restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

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
    video_url = str(request.url)
    file_id = str(uuid.uuid4())
    output_template = f"{DOWNLOAD_DIR}/{file_id}.%(ext)s"

    logger.info(f"Starting download for URL: {video_url}")

    try:
        # Run yt-dlp to download audio-only stream without conversion
        result = subprocess.run([
            "yt-dlp",
            "-f", "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",  # Download best audio stream
            "--no-playlist",  # Don't download playlists
            "--no-post-overwrites",  # Don't overwrite files
            "-o", output_template,
            video_url
        ], check=True, capture_output=True, text=True, timeout=300)  # 5 minute timeout

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
        
    except subprocess.TimeoutExpired:
        logger.error(f"Download timeout for URL: {video_url}")
        raise HTTPException(status_code=408, detail="Download timeout - video may be too long")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logger.error(f"yt-dlp error for URL {video_url}: {error_msg}")
        
        # Check if it's an ffmpeg-related error
        if "ffmpeg" in error_msg.lower() or "ffprobe" in error_msg.lower():
            raise HTTPException(
                status_code=500, 
                detail="Audio conversion failed. Please install ffmpeg: https://ffmpeg.org/download.html"
            )
        
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