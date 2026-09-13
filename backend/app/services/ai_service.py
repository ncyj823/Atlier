"""
app/services/ai_service.py — Google Gemini integration for NLP schedule parsing
and voice transcription (replaces OpenAI/Whisper-1).

Provider : Google Gemini (gemini-2.0-flash) via the google-genai SDK (v2.x+).
Key      : GEMINI_API_KEY in .env  =>  settings.gemini_api_key
Free tier: https://aistudio.google.com/apikey

Public API (unchanged -- no other file needs to be touched):
  parse_schedule(text, default_tz)  -> dict
  transcribe_audio(data, filename, content_type) -> str

Note: The openai_api_key field in config.py is kept for rollback; the route-level
guards that check it will silently pass (it defaults to "") and the real key
enforcement happens inside these functions.
"""
import asyncio
import base64
import json
import logging
import re
from datetime import datetime, timezone

import pytz
from google import genai
from google.genai import types as genai_types

from app.config import settings

logger = logging.getLogger(__name__)

# -- NLP system prompt ---------------------------------------------------------
# Content is identical to the original OpenAI prompt so scheduling behaviour
# is preserved exactly.
_NLP_SYSTEM = """You are a scheduling parser for a fashion freelancer's app. Convert the user's text into strict JSON.

Output ONLY a JSON object with these keys:
{
  "title": string,
  "mode": "design_call" | "measurement_call" | "sending_pieces" | "personal",
  "client_name": string | null,
  "start_iso": string (ISO 8601 with timezone offset),
  "duration_minutes": integer (default 30),
  "timezone": string (IANA tz, e.g. "Asia/Kolkata"),
  "notes": string
}

Rules:
- If the user says IST / India, use Asia/Kolkata.
- "coming Wednesday" / "next Wednesday" means the next upcoming Wednesday from CURRENT_DATETIME.
- Infer mode from keywords: "design"/"call" -> design_call; "measurement"/"fitting" -> measurement_call; "send"/"deliver"/"ship" -> sending_pieces; otherwise -> personal.
- start_iso must include the timezone offset (e.g. "2026-05-21T18:00:00+05:30").
- No prose, no markdown fences. Just raw JSON.
"""

# -- Gemini JSON response schema for parse_schedule ----------------------------
# Using a schema dict so the model is constrained to the exact structure that
# events.py expects. This eliminates the risk of Gemini drifting to different
# field names vs. what OpenAI used to return.
_SCHEDULE_SCHEMA = {
    "type": "object",
    "properties": {
        "title":            {"type": "string"},
        "mode":             {
            "type": "string",
            "enum": ["design_call", "measurement_call", "sending_pieces", "personal"],
        },
        "client_name":      {"type": "string", "nullable": True},
        "start_iso":        {"type": "string"},
        "duration_minutes": {"type": "integer"},
        "timezone":         {"type": "string"},
        "notes":            {"type": "string"},
    },
    "required": ["title", "mode", "start_iso", "duration_minutes", "timezone", "notes"],
}

# -- MIME type helpers ---------------------------------------------------------
_EXT_TO_MIME: dict = {
    ".m4a":  "audio/mp4",
    ".mp4":  "audio/mp4",
    ".mp3":  "audio/mpeg",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
    ".wav":  "audio/wav",
    ".webm": "audio/webm",
    ".ogg":  "audio/ogg",
}
_CONTENT_TYPE_NORMALISE: dict = {
    "audio/m4a":   "audio/mp4",
    "audio/x-m4a": "audio/mp4",
    "audio/x-wav": "audio/wav",
    "audio/mp3":   "audio/mpeg",
}


def _resolve_audio_mime(filename: str, content_type: str) -> str:
    """Return a Gemini-accepted MIME type from filename extension or Content-Type."""
    if "." in (filename or ""):
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        if ext in _EXT_TO_MIME:
            return _EXT_TO_MIME[ext]
    ct = (content_type or "").lower()
    return _CONTENT_TYPE_NORMALISE.get(ct, ct or "audio/mp4")


def _get_client() -> genai.Client:
    """Return a configured Gemini Client."""
    return genai.Client(api_key=settings.gemini_api_key)


def _extract_json(text: str) -> dict:
    """Strip optional ```json fences and parse the first JSON object found.

    Kept as a safety-net fallback even though Gemini JSON mode returns clean
    JSON -- defensive parsing is cheap insurance.
    """
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(m.group(0))


# -- Public API ----------------------------------------------------------------

async def parse_schedule(text: str, default_tz: str = "Asia/Kolkata") -> dict:
    """
    Send a free-text scheduling request to Gemini and return the parsed
    JSON dict containing title, mode, start_iso, duration_minutes, etc.

    The JSON schema is enforced via Gemini response_mime_type + response_schema
    so the output structure matches exactly what the rest of the app expects.

    Raises:
        RuntimeError -- if GEMINI_API_KEY is not configured
        ValueError   -- if the LLM response cannot be parsed as JSON
        Exception    -- any Gemini API error (passed through to the route handler)
    """
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    now_human = (
        datetime.now(timezone.utc)
        .astimezone(pytz.timezone(default_tz))
        .isoformat()
    )
    user_prompt = (
        f"CURRENT_DATETIME: {now_human}\n"
        f"DEFAULT_TIMEZONE: {default_tz}\n\n"
        f"{text}"
    )

    client = _get_client()

    # Gemini SDK is synchronous -- run in a thread to keep FastAPI non-blocking.
    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.0-flash",
        contents=user_prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=_NLP_SYSTEM,
            response_mime_type="application/json",
            response_schema=_SCHEDULE_SCHEMA,
        ),
    )

    raw = response.text or ""
    logger.debug("Gemini parse_schedule raw response: %s", raw[:500])
    return _extract_json(raw)


async def transcribe_audio(data: bytes, filename: str, content_type: str) -> str:
    """
    Send audio bytes to Gemini (gemini-2.0-flash) and return the transcription.

    Audio is uploaded as inline bytes via Part.from_bytes() -- no temp files.
    Gemini multimodal audio understanding replaces OpenAI Whisper-1.

    Args:
        data         -- raw audio bytes
        filename     -- original filename (used to detect file extension / MIME)
        content_type -- MIME type (fallback when extension is absent or unknown)

    Returns:
        Transcription text string (may be empty for silent audio).

    Raises:
        RuntimeError -- if GEMINI_API_KEY is not configured
        ValueError   -- if data is empty
        Exception    -- any Gemini API error (passed through to the route handler)
    """
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    if not data:
        raise ValueError("Empty audio data")

    mime = _resolve_audio_mime(filename, content_type)

    client = _get_client()

    # Gemini SDK is synchronous -- run in a thread to keep FastAPI non-blocking.
    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.0-flash",
        contents=[
            genai_types.Part.from_bytes(data=data, mime_type=mime),
            "Transcribe the speech in this audio clip. "
            "Return only the spoken words, verbatim. "
            "If the audio is silent or contains no speech, return an empty string.",
        ],
    )

    raw = (response.text or "").strip()
    logger.debug("Gemini transcribe_audio response length: %d chars", len(raw))
    return raw
