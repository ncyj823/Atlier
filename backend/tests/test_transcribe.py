"""tests/test_transcribe.py — Voice transcription endpoint tests."""
import io
import wave
import pytest
import requests
from tests.conftest import BASE_URL, API_KEY

API = f"{BASE_URL}/api"
HEADERS = {"X-API-Key": API_KEY}  # No Content-Type — multipart sets its own


def _make_silent_wav(duration_seconds: int = 1) -> bytes:
    """Create a minimal WAV file with silence for testing."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000 * duration_seconds)
    return buf.getvalue()


def test_transcribe_empty_audio_returns_400():
    """Empty audio data must be rejected with 400."""
    files = {"audio": ("empty.wav", b"", "audio/wav")}
    r = requests.post(
        f"{API}/transcribe",
        files=files,
        headers=HEADERS,
        timeout=20,
    )
    assert r.status_code in (400, 422), r.text


def test_transcribe_requires_auth():
    """Transcribe without API key must return 401."""
    audio_bytes = _make_silent_wav()
    files = {"audio": ("silent.wav", audio_bytes, "audio/wav")}
    r = requests.post(f"{API}/transcribe", files=files, timeout=20)
    assert r.status_code == 401


@pytest.mark.skipif(not API_KEY, reason="API_KEY not set")
def test_transcribe_silent_wav():
    """
    Silent WAV should return 200 with a text field.
    Whisper may return empty string or occasional hallucination for silence.
    """
    audio_bytes = _make_silent_wav()
    files = {"audio": ("silent.wav", audio_bytes, "audio/wav")}
    r = requests.post(
        f"{API}/transcribe",
        files=files,
        headers=HEADERS,
        timeout=60,
    )
    if r.status_code == 500 and "LLM key not configured" in r.text:
        pytest.skip("GEMINI_API_KEY not configured on this server")
    assert r.status_code == 200, r.text
    j = r.json()
    assert "text" in j
    assert isinstance(j["text"], str)
