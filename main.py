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
import time
import random
import ssl
import certifi

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

# Rate limiting - track last request time
last_request_time = 0
MIN_REQUEST_INTERVAL = 5  # Increased to 5 seconds between requests

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

def get_yt_dlp_command(video_url: str, output_template: str, attempt: int = 1):
    """Generate yt-dlp command with comprehensive anti-bot detection measures"""
    
    # Different user agents for rotation
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
    ]
    
    # Base command with SSL fixes
    cmd = [
        "yt-dlp",
        "-f", "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
        "--no-playlist",
        "--no-post-overwrites",
        "-o", output_template,
        "--user-agent", user_agents[attempt % len(user_agents)],
        # SSL and certificate fixes
        "--no-check-certificate",
        "--prefer-insecure",
        "--http-chunk-size", "10485760",  # 10MB chunks
        # Additional SSL options
        "--no-ssl-verify",
        "--http-chunk-size", "5242880",  # 5MB chunks
        # Browser-like headers
        "--add-header", "Accept-Language:en-US,en;q=0.9,en-GB;q=0.8",
        "--add-header", "Accept-Encoding:gzip, deflate, br",
        "--add-header", "DNT:1",
        "--add-header", "Connection:keep-alive",
        "--add-header", "Upgrade-Insecure-Requests:1",
        "--add-header", "Sec-Fetch-Dest:document",
        "--add-header", "Sec-Fetch-Mode:navigate",
        "--add-header", "Sec-Fetch-Site:none",
        "--add-header", "Sec-Fetch-User:?1",
        "--add-header", "Cache-Control:max-age=0",
        # Additional anti-detection measures
        "--sleep-interval", "2",
        "--max-sleep-interval", "5",
        "--retry-sleep", "exponential",
        "--fragment-retries", "10",
        "--retries", "10",
    ]
    
    # Add cookies if available
    cookies_path = "cookies.txt"
    if os.path.exists(cookies_path):
        cmd.extend(["--cookies", cookies_path])
    
    # Different strategies for different attempts
    if attempt == 1:
        cmd.extend(["--extractor-args", "youtube:player_client=android"])
    elif attempt == 2:
        cmd.extend(["--extractor-args", "youtube:player_client=web"])
    else:
        cmd.extend(["--extractor-args", "youtube:player_client=web;player_skip=webpage"])
    
    cmd.append(video_url)
    return cmd

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {"status": "healthy", "service": "youtube-audio-downloader"}

@app.post("/download")
async def download_youtube_audio(request: YouTubeDownloadRequest):
    global last_request_time
    
    # Rate limiting with exponential backoff
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

    # Try multiple attempts with different strategies
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"Attempt {attempt}/{max_attempts}")
            
            # Add random delay before each attempt
            if attempt > 1:
                delay = random.uniform(3, 8)
                logger.info(f"Waiting {delay:.1f} seconds before retry")
                await asyncio.sleep(delay)
            
            # Get command for this attempt
            cmd = get_yt_dlp_command(video_url, output_template, attempt)
            
            # Set environment variables for SSL
            env = os.environ.copy()
            env['PYTHONHTTPSVERIFY'] = '0'
            env['REQUESTS_CA_BUNDLE'] = certifi.where()
            
            # Run yt-dlp with extended timeout and environment
            result = subprocess.run(
                cmd,
                check=True, 
                capture_output=True, 
                text=True, 
                timeout=300,
                env=env
            )

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
            logger.error(f"Download timeout for URL: {video_url} (attempt {attempt})")
            if attempt == max_attempts:
                raise HTTPException(status_code=408, detail="Download timeout - video may be too long")
            continue
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            logger.error(f"yt-dlp error for URL {video_url} (attempt {attempt}): {error_msg}")
            
            # Check if it's an ffmpeg-related error
            if "ffmpeg" in error_msg.lower() or "ffprobe" in error_msg.lower():
                raise HTTPException(
                    status_code=500, 
                    detail="Audio conversion failed. Please install ffmpeg: https://ffmpeg.org/download.html"
                )
            
            # Check for bot detection errors
            if any(keyword in error_msg.lower() for keyword in ["bot", "429", "too many requests", "precondition check failed", "sign in to confirm"]):
                if attempt < max_attempts:
                    # Wait longer before retry for bot detection
                    wait_time = random.uniform(10, 20)
                    logger.info(f"Bot detection detected, waiting {wait_time:.1f} seconds before retry")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise HTTPException(
                        status_code=429,
                        detail="YouTube is blocking automated requests. Please try again later or use a different video."
                    )
            
            # Check for SSL errors
            if "ssl" in error_msg.lower() or "certificate" in error_msg.lower():
                if attempt < max_attempts:
                    logger.info(f"SSL error detected, retrying with different settings")
                    continue
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="SSL certificate verification failed. Please try again later."
                    )
            
            # For other errors, try again if we have attempts left
            if attempt < max_attempts:
                await asyncio.sleep(random.uniform(2, 5))
                continue
            else:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Failed to download audio after {max_attempts} attempts: {error_msg}"
                )
                
        except Exception as e:
            logger.error(f"Unexpected error for URL {video_url} (attempt {attempt}): {str(e)}")
            if attempt == max_attempts:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Unexpected error: {str(e)}"
                )
            continue

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)