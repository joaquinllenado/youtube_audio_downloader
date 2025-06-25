# YouTube Downloader Microservice

A FastAPI microservice that downloads YouTube videos as audio files.

## Features

- Download YouTube videos as audio files (m4a, webm, opus formats)
- Automatic file cleanup after download
- Health check endpoint for monitoring
- CORS support for web applications
- Request validation and error handling
- Logging for debugging and monitoring

## Setup

### Local Development

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Install yt-dlp (required for YouTube downloads):
```bash
pip install yt-dlp
```

3. Install ffmpeg (required for audio conversion):
   - **Windows**: Download from https://ffmpeg.org/download.html or use `winget install ffmpeg`
   - **macOS**: `brew install ffmpeg`
   - **Linux**: `sudo apt install ffmpeg` (Ubuntu/Debian) or `sudo yum install ffmpeg` (CentOS/RHEL)

4. Start the server:
```bash
uvicorn main:app --reload
```

### Docker Deployment

1. Build the Docker image:
```bash
docker build -t youtube-downloader .
```

2. Run the container:
```bash
docker run -p 8000:8000 youtube-downloader
```

## API Endpoints

### Health Check
- `GET /health` - Check service health status

### Download Audio
- `POST /download` - Download YouTube video as audio file

**Request Body:**
```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID"
}
```

**Response:** Audio file download

## Production Considerations

1. **CORS Configuration**: Update the `allow_origins` in `main.py` to restrict to your domain
2. **Rate Limiting**: Consider adding rate limiting for production use
3. **Monitoring**: Use the `/health` endpoint for health checks
4. **Logging**: Logs are configured for production monitoring
5. **File Cleanup**: Files are automatically cleaned up after serving

## Security Notes

⚠️ **Important Security Considerations:**
- This service downloads files from YouTube URLs provided by users
- Always validate and sanitize input URLs in production
- Consider implementing rate limiting to prevent abuse
- Update CORS settings to only allow your domain
- Monitor disk usage as files are temporarily stored
- Consider adding authentication if needed for your use case

## Error Handling

The service handles various error scenarios:
- Invalid YouTube URLs
- Download timeouts (5-minute limit)
- Missing ffmpeg installation
- Network errors
- File system errors

All errors return appropriate HTTP status codes and descriptive messages. 