"""
app/database.py — Shared Motor (async MongoDB) client.

A single AsyncIOMotorClient is created at startup and closed at shutdown.
Never create a new connection per request — use the `db` instance exported here.
"""
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import settings

logger = logging.getLogger(__name__)

# Module-level client and db — populated during app lifespan startup.
_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_client() -> AsyncIOMotorClient:
    if _client is None:
        raise RuntimeError("Database client not initialised. Call connect_db() first.")
    return _client


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialised. Call connect_db() first.")
    return _db


async def connect_db() -> None:
    """Open the Motor connection. Called once at application startup."""
    global _client, _db
    try:
        _client = AsyncIOMotorClient(
            settings.mongo_url,
            serverSelectionTimeoutMS=5_000,
            connectTimeoutMS=5_000,
        )
        _db = _client[settings.db_name]
        # Ping to verify connectivity eagerly at startup (raises on failure).
        await _client.admin.command("ping")
        logger.info("MongoDB connected — database: %s", settings.db_name)
    except Exception as exc:
        logger.error("MongoDB connection failed at startup: %s", exc)
        # Re-raise so Uvicorn surfaces the error and stops instead of silently
        # serving requests that will all fail with opaque 500s.
        raise


async def close_db() -> None:
    """Close the Motor connection. Called once at application shutdown."""
    global _client, _db
    if _client:
        _client.close()
        logger.info("MongoDB connection closed")
    _client = None
    _db = None


async def ping_db() -> float:
    """
    Ping MongoDB and return round-trip latency in milliseconds.
    Raises an exception if the ping fails.
    """
    import time
    db = get_db()
    t0 = time.monotonic()
    await db.command("ping")
    return round((time.monotonic() - t0) * 1000, 2)


# Convenience accessor so route modules can do:
#   from app.database import db
# and use db.clients.find_one(...) etc.
class _DBProxy:
    """Lazy proxy — resolves to the live db object on first attribute access."""

    def __getattr__(self, name: str):
        return getattr(get_db(), name)

    def __getitem__(self, name: str):
        return get_db()[name]


db: AsyncIOMotorDatabase = _DBProxy()  # type: ignore[assignment]
