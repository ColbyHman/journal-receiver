from fastapi import FastAPI, Request, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import httpx
import certifi
import ssl
import os
import aiofiles
from pathlib import Path
from typing import Optional
import logging
from datetime import datetime
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Journal Receiver", version="1.0.0")

# Configuration
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "./uploads")
FORWARD_API_URL = os.getenv("FORWARD_API_URL", None)
FORWARD_API_TIMEOUT = int(os.getenv("FORWARD_API_TIMEOUT", "30"))
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "50")) * 1024 * 1024  # 50MB default
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "https://n8n.colbyh.dev/webhook/cee60c52-a5a1-49ce-a4de-07aa1574e56c")
ssl_context = ssl.create_default_context()
ssl_context.load_verify_locations(certifi.where())  # add certifi bundle too

# Create upload directory if it doesn't exist
Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

async def forward_to_api(file_path: str, filename: str):
    """Forward the audio file to a second API if configured"""
    if not FORWARD_API_URL:
        logger.info("No forward API URL configured, skipping forwarding")
        return
    
    try:
        async with httpx.AsyncClient(timeout=FORWARD_API_TIMEOUT) as client:
            with open(file_path, "rb") as f:
                files = {"file": (filename, f, "audio/mpeg")}
                response = await client.post(FORWARD_API_URL, files=files)
                response.raise_for_status()
                logger.info(f"Successfully forwarded {filename} to {FORWARD_API_URL}")
    except httpx.TimeoutException:
        logger.error(f"Timeout when forwarding {filename} to {FORWARD_API_URL}")
    except Exception as e:
        logger.error(f"Error forwarding {filename} to {FORWARD_API_URL}: {str(e)}")

@app.post("/upload-audio")
async def upload_audio(request: Request, background_tasks: BackgroundTasks):
    contents = await request.body()
    if not contents:
        raise HTTPException(status_code=400, detail="No content in request body")

    # Generate filename — no original filename available from raw body
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    filename = f"{timestamp}_{unique_id}.m4a"  # or .mp3, whatever you expect

    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "./uploads")
    Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
    file_path = os.path.join(UPLOAD_FOLDER, filename)

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(contents)

    logging.info(f"Saved raw upload file: {filename} ({len(contents)} bytes)")

    # Optionally forward or other logic...

    async with httpx.AsyncClient(timeout=FORWARD_API_TIMEOUT, verify=ssl_context) as client:
        try:
            files = {
            "file": (filename, contents, "audio/mp4")  # or appropriate audio MIME type
        }
            response = await client.post(
                N8N_WEBHOOK_URL,
                files=files,
                data={"filename": filename, "size_bytes": str(len(contents))}  # optional extra form fields
            )
            response.raise_for_status()
            logging.info(f"Successfully notified n8n webhook for {filename}")
        except httpx.RequestError as e:
            logging.error(f"Failed to notify n8n webhook: {str(e)}")

    return {
        "message": "Raw file uploaded successfully",
        "filename": filename,
        "size_bytes": len(contents),
        "saved_path": file_path,
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "audio-upload-service"}

@app.get("/")
async def root():
    """Root endpoint with service info"""
    return {
        "service": "Audio Upload Service",
        "version": "1.0.0",
        "endpoints": [
            "POST /upload-audio - Upload audio file",
            "GET /health - Health check",
            "GET / - This endpoint"
        ]
    }

# For Lambda deployment
try:
    from mangum import Mangum
    handler = Mangum(app)
except ImportError:
    # Mangum not installed, running in regular mode
    pass

def run():
    import uvicorn
    uvicorn.run("journal_receiver.main:app", host="0.0.0.0", port=8000, reload=True)
