"""
app/routes/seed.py — Demo data seeding endpoint.

POST /api/_seed

Inserts 3 demo clients if the clients collection is empty.
Idempotent — safe to call multiple times. Returns {ok: True, skipped: True}
if data already exists.
"""
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from app.database import db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["seed"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/_seed")
async def seed_demo():
    """
    Insert demo clients if the database is empty. Safe to call repeatedly.
    """
    if await db.clients.count_documents({}) > 0:
        return {"ok": True, "skipped": True}

    demo = [
        {
            "id": str(uuid.uuid4()),
            "name": "Anaïs Mehta",
            "whatsapp": "+91 98765 12345",
            "email": "anais@example.com",
            "measurements": {
                "Bust": '34"',
                "Waist": '26"',
                "Hip": '36"',
                "Shoulder": '14"',
            },
            "notes": "Prefers structured silhouettes.",
            "created_at": _now_iso(),
            "avatar_url": None,
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Riya Kapoor",
            "whatsapp": "+91 99887 66554",
            "email": "riya@example.com",
            "measurements": {"Bust": '32"', "Waist": '24"', "Hip": '34"'},
            "notes": "Loves silk crepe and earthy tones.",
            "created_at": _now_iso(),
            "avatar_url": None,
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Leah Sinha",
            "whatsapp": "",
            "email": "",
            "measurements": {},
            "notes": "",
            "created_at": _now_iso(),
            "avatar_url": None,
        },
    ]

    await db.clients.insert_many(demo)
    logger.info("Seeded %d demo clients", len(demo))
    return {"ok": True, "count": len(demo)}
