"""tests/test_ai_service.py - Unit tests for the Gemini-backed ai_service.

All tests mock google.genai so no real API calls are made.
Uses asyncio.run() for async test execution (compatible with Python 3.14+).
"""
import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch


# -- Helpers -------------------------------------------------------------------

def _fake_response(text: str) -> MagicMock:
    """Return a mock that mimics a google.genai GenerateContentResponse."""
    r = MagicMock()
    r.text = text
    return r


_VALID_PARSE_PAYLOAD = json.dumps({
    "title": "Design call with Priya",
    "mode": "design_call",
    "client_name": "Priya",
    "start_iso": "2026-09-15T15:00:00+05:30",
    "duration_minutes": 30,
    "timezone": "Asia/Kolkata",
    "notes": "",
})


# -- parse_schedule tests ------------------------------------------------------

class TestParseSchedule:

    @patch("app.services.ai_service.settings")
    @patch("app.services.ai_service.genai")
    def test_parse_schedule_success(self, mock_genai, mock_settings):
        """Valid Gemini JSON response returns the expected dict."""
        mock_settings.gemini_api_key = "fake-key"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _fake_response(_VALID_PARSE_PAYLOAD)
        mock_genai.Client.return_value = mock_client

        from app.services import ai_service
        result = asyncio.run(
            ai_service.parse_schedule("Design call with Priya next Monday at 3pm IST")
        )

        assert result["title"] == "Design call with Priya"
        assert result["mode"] == "design_call"
        assert result["start_iso"] == "2026-09-15T15:00:00+05:30"
        assert result["duration_minutes"] == 30

    @patch("app.services.ai_service.settings")
    def test_parse_schedule_no_key_raises(self, mock_settings):
        """Missing GEMINI_API_KEY must raise RuntimeError."""
        mock_settings.gemini_api_key = ""
        from app.services import ai_service
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            asyncio.run(ai_service.parse_schedule("Call with Priya"))

    @patch("app.services.ai_service.settings")
    @patch("app.services.ai_service.genai")
    def test_parse_schedule_malformed_json_raises(self, mock_genai, mock_settings):
        """Gemini returning prose instead of JSON must raise ValueError."""
        mock_settings.gemini_api_key = "fake-key"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _fake_response(
            "Sure! Let me help you schedule a call."
        )
        mock_genai.Client.return_value = mock_client

        from app.services import ai_service
        with pytest.raises(ValueError, match="No JSON"):
            asyncio.run(ai_service.parse_schedule("Call with Priya"))


# -- transcribe_audio tests ----------------------------------------------------

class TestTranscribeAudio:

    @patch("app.services.ai_service.settings")
    @patch("app.services.ai_service.genai")
    def test_transcribe_success(self, mock_genai, mock_settings):
        """Valid audio bytes return transcription text."""
        mock_settings.gemini_api_key = "fake-key"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _fake_response(
            "Design call with Priya on Monday"
        )
        mock_genai.Client.return_value = mock_client

        from app.services import ai_service
        result = asyncio.run(
            ai_service.transcribe_audio(b"\x00\x01\x02", "recording.wav", "audio/wav")
        )
        assert result == "Design call with Priya on Monday"

    @patch("app.services.ai_service.settings")
    def test_transcribe_no_key_raises(self, mock_settings):
        """Missing GEMINI_API_KEY must raise RuntimeError."""
        mock_settings.gemini_api_key = ""
        from app.services import ai_service
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            asyncio.run(ai_service.transcribe_audio(b"\x00", "x.wav", "audio/wav"))

    @patch("app.services.ai_service.settings")
    def test_transcribe_empty_bytes_raises(self, mock_settings):
        """Empty audio data must raise ValueError."""
        mock_settings.gemini_api_key = "fake-key"
        from app.services import ai_service
        with pytest.raises(ValueError, match="Empty audio"):
            asyncio.run(ai_service.transcribe_audio(b"", "x.wav", "audio/wav"))

    @patch("app.services.ai_service.settings")
    @patch("app.services.ai_service.genai")
    def test_transcribe_silent_returns_empty_string(self, mock_genai, mock_settings):
        """Gemini returning empty string for silent audio propagates cleanly."""
        mock_settings.gemini_api_key = "fake-key"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _fake_response("")
        mock_genai.Client.return_value = mock_client

        from app.services import ai_service
        result = asyncio.run(
            ai_service.transcribe_audio(b"\x00" * 100, "silent.wav", "audio/wav")
        )
        assert result == ""


# -- MIME resolution tests ------------------------------------------------------

class TestResolveAudioMime:

    def test_wav_extension(self):
        from app.services.ai_service import _resolve_audio_mime
        assert _resolve_audio_mime("clip.wav", "") == "audio/wav"

    def test_m4a_extension(self):
        from app.services.ai_service import _resolve_audio_mime
        assert _resolve_audio_mime("rec.m4a", "") == "audio/mp4"

    def test_content_type_fallback(self):
        from app.services.ai_service import _resolve_audio_mime
        assert _resolve_audio_mime("noext", "audio/x-m4a") == "audio/mp4"

    def test_unknown_falls_back_to_mp4(self):
        from app.services.ai_service import _resolve_audio_mime
        assert _resolve_audio_mime("noext", "") == "audio/mp4"
