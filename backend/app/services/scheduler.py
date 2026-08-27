"""
app/services/scheduler.py — APScheduler-based email reminder jobs.

Schedules three reminder emails for each calendar event:
  1. Morning of the event (9:00 AM local time)
  2. 30 minutes before
  3. At event start time

Jobs are stored in memory (MemoryJobStore), so they are lost on restart.
On application startup, all upcoming events are re-read from MongoDB and
their reminders are re-scheduled to survive restarts/deploys.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from dateutil import parser as date_parser

from app.config import settings

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# Global scheduler instance — started during app lifespan.
scheduler = AsyncIOScheduler(
    jobstores={"default": MemoryJobStore()},
    timezone=pytz.UTC,
)

REMINDER_LABELS = {
    "morning_of": "the morning of",
    "thirty_min": "in 30 minutes",
    "now": "starting now",
}


def reminders_for(start_iso: str) -> list[str]:
    """
    Return the three reminder timestamps for an event:
    [9am same day, 30min before, at start].
    These are stored in the event document and returned to the mobile app.
    """
    try:
        dt = date_parser.isoparse(start_iso)
    except Exception:
        return []
    morning = dt.replace(hour=9, minute=0, second=0, microsecond=0)
    return [
        morning.isoformat(),
        (dt - timedelta(minutes=30)).isoformat(),
        dt.isoformat(),
    ]


def _fire_reminder(event_id: str, kind: str) -> None:
    """
    APScheduler job — re-loads event from MongoDB at fire time (avoids stale
    closure data) and sends reminder emails to client + owner.
    """
    import asyncio as _aio

    async def _do():
        # Import here to avoid circular imports at module load time.
        from app.database import db
        from app.services.email_service import send_email, meeting_html

        ev = await db.events.find_one({"id": event_id}, {"_id": 0})
        if not ev:
            return

        try:
            dt = date_parser.isoparse(ev["start_iso"])
            when_human = dt.strftime("%A, %d %b %Y · %I:%M %p %Z")
        except Exception:
            when_human = ev["start_iso"]

        label = REMINDER_LABELS.get(kind, "soon")
        subject = f"Reminder · {ev['title']} — {label}"
        html = meeting_html(
            f"{ev['title']} ({label})",
            when_human,
            ev.get("meet_link", ""),
            ev.get("notes", ""),
        )

        recipients = set()
        if ev.get("client_email"):
            recipients.add(ev["client_email"])
        if settings.gmail_user:
            recipients.add(settings.gmail_user)

        for r in recipients:
            await send_email(r, subject, html)

    try:
        _aio.run(_do())
    except Exception as exc:
        logger.error("_fire_reminder event_id=%s kind=%s failed: %s", event_id, kind, exc)


def schedule_event_reminders(event_id: str, start_iso: str) -> None:
    """
    Schedule (or re-schedule) the three reminder jobs for an event.
    Any pre-existing jobs for this event_id are cancelled first.
    Jobs more than 10 seconds in the past are silently skipped.
    """
    # Cancel existing reminders for this event
    for kind in ("morning_of", "thirty_min", "now"):
        try:
            scheduler.remove_job(f"rem-{event_id}-{kind}")
        except Exception:
            pass

    try:
        dt = date_parser.isoparse(start_iso)
    except Exception:
        logger.warning("schedule_event_reminders: invalid start_iso %r", start_iso)
        return

    now = datetime.now(timezone.utc)
    morning = dt.replace(hour=9, minute=0, second=0, microsecond=0)
    thirty = dt - timedelta(minutes=30)

    for when, kind in [
        (morning, "morning_of"),
        (thirty, "thirty_min"),
        (dt, "now"),
    ]:
        if when <= now + timedelta(seconds=10):
            continue  # already past — skip silently
        try:
            scheduler.add_job(
                _fire_reminder,
                "date",
                run_date=when,
                args=[event_id, kind],
                id=f"rem-{event_id}-{kind}",
                replace_existing=True,
                misfire_grace_time=600,
            )
        except Exception as exc:
            logger.error(
                "schedule_event_reminders: failed for kind=%s: %s", kind, exc
            )


def cancel_event_reminders(event_id: str) -> None:
    """Cancel all three pending reminder jobs for an event."""
    for kind in ("morning_of", "thirty_min", "now"):
        try:
            scheduler.remove_job(f"rem-{event_id}-{kind}")
        except Exception:
            pass


async def reconcile_reminders_on_startup(db) -> None:
    """
    Re-schedule reminders for all upcoming events after a restart.

    APScheduler uses MemoryJobStore, so all jobs are lost on process restart.
    This function re-derives them from MongoDB so deploys don't silently drop
    pending reminder emails.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = db.events.find(
            {"start_iso": {"$gte": now}},
            {"_id": 0, "id": 1, "start_iso": 1},
        )
        n = 0
        async for ev in cursor:
            schedule_event_reminders(ev["id"], ev["start_iso"])
            n += 1
        logger.info("Re-scheduled reminders for %d upcoming event(s) after restart", n)
    except Exception as exc:
        logger.error("reminder reconciliation on startup failed: %s", exc)
