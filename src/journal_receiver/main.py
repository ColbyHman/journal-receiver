from fastapi import FastAPI, Request, HTTPException
import httpx
import certifi
import ssl

from dotenv import load_dotenv
import os

import aiofiles
from pathlib import Path

import logging
from datetime import datetime
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Journal Receiver", version="1.0.0")

load_dotenv()

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "./uploads")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "50")) * 1024 * 1024  # 50MB default
FORWARD_API_TIMEOUT = int(os.getenv("FORWARD_API_TIMEOUT", "30"))
SAVE_LOCAL = os.getenv("SAVE_LOCAL", "false").lower() == "true"

ssl_context = ssl.create_default_context()
ssl_context.load_verify_locations(certifi.where())

Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

@app.post("/upload-audio")
async def upload_audio(request: Request):
    contents = await request.body()
    if not contents:
        raise HTTPException(status_code=400, detail="No content in request body")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    filename = f"{timestamp}_{unique_id}.m4a"

    if SAVE_LOCAL:
        UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "./uploads")
        Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(contents)
        logging.info(f"Saved raw upload file: {filename} ({len(contents)} bytes)")

    async with httpx.AsyncClient(timeout=FORWARD_API_TIMEOUT, verify=ssl_context) as client:
        try:
            files = {
                "file": (filename, contents, "audio/mp4")
            }
            response = await client.post(
                N8N_WEBHOOK_URL,
                files=files,
                data={"filename": filename, "size_bytes": str(len(contents))}
            )
            response.raise_for_status()
            logging.info(f"Successfully notified n8n webhook for {filename}")
        except httpx.RequestError as e:
            logging.error(f"Failed to notify n8n webhook: {str(e)}")

    return {
        "message": "Raw file uploaded successfully",
        "filename": filename,
        "size_bytes": len(contents),
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

def run():
    import uvicorn
    uvicorn.run("journal_receiver.main:app", host="0.0.0.0", port=8000, reload=True)
