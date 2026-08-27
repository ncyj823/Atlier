"""
app/routes/health.py — Health check endpoints.

GET /health    → {status: "ok"}
GET /health/db → {status: "ok", latency_ms: N} or {status: "error", detail: ...}

These endpoints require NO authentication so they can be hit by load balancers,
container orchestrators, and deployment scripts without an API key.
"""
import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.database import ping_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Basic liveness check. Returns immediately without touching the database."""
    return {"status": "ok"}


@router.get("/health/db")
async def health_db() -> JSONResponse:
    """
    Database readiness check. Pings MongoDB and reports round-trip latency.
    Returns HTTP 503 if the database is unreachable.
    """
    try:
        latency_ms = await ping_db()
        return JSONResponse(
            content={"status": "ok", "latency_ms": latency_ms},
            status_code=200,
        )
    except Exception as exc:
        logger.error("Health DB check failed: %s", exc)
        return JSONResponse(
            content={"status": "error", "detail": "Database unreachable"},
            status_code=503,
        )
