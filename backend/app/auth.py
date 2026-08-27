"""
app/auth.py — X-API-Key authentication dependency.

Every /api route (except the public share page) uses:
    dependencies=[Depends(require_api_key)]

Behaviour (preserved from original server.py):
  - API_KEY not set in env  → 500  (fail closed — never silently run without auth)
  - Header missing/wrong    → 401
  - Header correct          → request proceeds
"""
import secrets
import logging
from fastapi import Header, HTTPException
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """
    FastAPI dependency that validates the X-API-Key header.

    Raises:
        HTTPException 500 — if API_KEY is not configured (misconfigured server)
        HTTPException 401 — if the header is missing or does not match
    """
    if not settings.api_key:
        # Fail closed: an app managing client PII and financials must never
        # run with authentication silently disabled because API_KEY was not set.
        logger.critical(
            "SERVER MISCONFIGURED: API_KEY environment variable is not set. "
            "Set API_KEY in your .env file and restart."
        )
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: API_KEY is not set",
        )

    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )
