"""
app/services/ai_service.py — OpenAI integration for NLP schedule parsing and
Whisper voice transcription.

Previously the app used EMERGENT_LLM_KEY as the env var name. The key value
is a standard OpenAI API key (sk-proj-...). This module now reads it from
OPENAI_API_KEY via settings. Behaviour is identical.

If OPENAI_BASE_URL is set, requests are routed through that base URL, which
allows switching to any OpenAI-compatible API provider without code changes.
"""
import json
import re
import logging
import tempfile
import os
from datetime import datetime, timezone

import pytz
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# ── NLP system prompt ─────────────────────────────────────────────────────────
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


def _get_client() -> AsyncOpenAI:
    """Return a configured AsyncOpenAI client using OPENAI_API_KEY."""
    return AsyncOpenAI(
        api_key=settings.openai_api_key or "unset",
        base_url=settings.openai_base_url or None,
    )


def _extract_json(text: str) -> dict:
    """Strip optional ```json fences and parse the first JSON object found."""
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(m.group(0))


async def parse_schedule(text: str, default_tz: str = "Asia/Kolkata") -> dict:
    """
    Send a free-text scheduling request to GPT-4.1 and return the parsed
    JSON dict containing title, mode, start_iso, duration_minutes, etc.

    Raises:
        RuntimeError — if OPENAI_API_KEY is not configured
        ValueError   — if the LLM response cannot be parsed as JSON
        Exception    — any OpenAI API error (passed through)
    """
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    now_human = (
        datetime.now(timezone.utc)
        .astimezone(pytz.timezone(default_tz))
        .isoformat()
    )
    sys_msg = (
        f"{_NLP_SYSTEM}\n\n"
        f"CURRENT_DATETIME: {now_human}\n"
        f"DEFAULT_TIMEZONE: {default_tz}"
    )

    client = _get_client()
    response = await client.responses.create(
        model="gpt-4.1",
        input=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": text},
        ],
    )
    return _extract_json(response.output_text)


async def transcribe_audio(data: bytes, filename: str, content_type: str) -> str:
    """
    Send audio bytes to OpenAI Whisper-1 and return the transcription text.

    Args:
        data         — raw audio bytes
        filename     — original filename (used to pick file extension)
        content_type — MIME type (fallback for extension detection)

    Returns:
        Transcription text string (may be empty for silent audio).

    Raises:
        RuntimeError — if OPENAI_API_KEY is not configured
        ValueError   — if data is empty
        Exception    — any OpenAI API error (passed through)
    """
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    if not data:
        raise ValueError("Empty audio data")

    # Resolve file extension from filename or MIME type
    _suffix_map = {
        "audio/m4a": ".m4a", "audio/x-m4a": ".m4a", "audio/mp4": ".m4a",
        "audio/mpeg": ".mp3", "audio/mp3": ".mp3",
        "audio/wav": ".wav", "audio/x-wav": ".wav",
        "audio/webm": ".webm", "audio/ogg": ".webm",
    }
    ext = ""
    if "." in (filename or ""):
        ext = "." + filename.rsplit(".", 1)[-1].lower()
    if ext not in {".m4a", ".mp3", ".wav", ".webm", ".mp4", ".mpeg", ".mpga"}:
        ext = _suffix_map.get(content_type or "", ".m4a")

    client = _get_client()

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as fh:
            transcription = await client.audio.transcriptions.create(
                model="whisper-1",
                file=fh,
            )
        return transcription.text.strip()
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
