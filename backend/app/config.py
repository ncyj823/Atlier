"""
app/config.py — All environment variables loaded once via pydantic-settings.

IMPORTANT: EMERGENT_LLM_KEY has been renamed to OPENAI_API_KEY.
Set OPENAI_API_KEY in your .env file with the same key value you previously
had in EMERGENT_LLM_KEY. The key itself is unchanged — only the name is.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── MongoDB ────────────────────────────────────────────────────────────────
    mongo_url: str
    db_name: str = "Atlier"

    # ── API authentication ─────────────────────────────────────────────────────
    # Every /api route (except public share page) requires X-API-Key: <API_KEY>
    api_key: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiration_days: int = 30

    # ── OpenAI (kept for rollback; no longer used by ai_service) ──────────────
    # Previously named EMERGENT_LLM_KEY — same key value, new name.
    openai_api_key: str = ""
    # Optional: override base URL if using an OpenAI-compatible proxy/provider.
    openai_base_url: str = ""

    # ── Google Gemini (NLP schedule parse + voice transcription) ──────────────
    # Get your free API key at: https://aistudio.google.com/apikey
    gemini_api_key: str = ""

    # ── Email (Gmail SMTP) ─────────────────────────────────────────────────────
    gmail_user: str = ""
    gmail_app_password: str = ""
    sender_email: str = ""

    # ── Public URL (used in share link generation) ─────────────────────────────
    public_base_url: str = "http://localhost:8000"

    # ── CORS ───────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins.
    # Example: "https://app.yourdomain.com,https://admin.yourdomain.com"
    allowed_origins: str = ""

    # ── Google Calendar (optional) ─────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_calendar_id: str = "primary"

    # ── Derived helpers ────────────────────────────────────────────────────────
    @property
    def gmail_password_clean(self) -> str:
        """Strip spaces from App Password (Google displays them grouped in 4s)."""
        return self.gmail_app_password.strip().replace(" ", "")

    @property
    def effective_sender_email(self) -> str:
        if self.sender_email:
            return self.sender_email
        if self.gmail_user:
            return f"Atelier <{self.gmail_user}>"
        return "Atelier"

    @property
    def cors_origins(self) -> list[str]:
        origins = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        default_origins = [
            "http://localhost:3000",
            "http://localhost:5173",
            "https://atlier-sigma.vercel.app"
        ]
        return list(set(origins + default_origins))

    @property
    def google_configured(self) -> bool:
        return bool(
            self.google_client_id
            and self.google_client_secret
            and self.google_refresh_token
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Convenience re-export so routes can do: from app.config import settings
settings: Settings = get_settings()
