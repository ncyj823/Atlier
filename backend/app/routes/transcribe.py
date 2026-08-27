"""
app/routes/transcribe.py — Voice-to-text transcription via OpenAI Whisper-1.

POST /api/transcribe  (multipart form — field: "audio")

Returns: {text: "transcribed text"}

Fails with:
  400 — empty audio data
  500 — OPENAI_API_KEY not configured, or Whisper call fails
"""
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.services import ai_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["transcribe"])


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Transcribe uploaded audio using OpenAI Whisper-1.

    Accepts common audio formats: m4a, mp3, wav, webm, mp4.
    Returns the transcription text (may be empty for silent audio).
    """
    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="LLM key not configured")

    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio")

    try:
        text = await ai_service.transcribe_audio(
            data=data,
            filename=audio.filename or "",
            content_type=audio.content_type or "",
        )
        return {"text": text}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Transcription failed: %s", exc)
        raise HTTPException(status_code=500, detail="Transcription failed")
