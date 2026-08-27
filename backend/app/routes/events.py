"""
app/routes/events.py — Calendar event routes + NLP schedule parsing.

Endpoints:
  POST /api/schedule/parse           — NLP text → structured event data
  POST /api/events                   — create event
  GET  /api/events                   — list events (with optional date range)
  PUT  /api/events/{event_id}        — reschedule event
  DELETE /api/events/{event_id}      — delete event
"""
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from dateutil import parser as date_parser
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.database import db
from app.models.common import ParseRequest
from app.models.event import EventCreate, EventOut, EventReschedule
from app.services import ai_service
from app.services import google_cal
from app.services.email_service import send_email_sync, meeting_html
from app.services.scheduler import (
    cancel_event_reminders,
    reminders_for,
    schedule_event_reminders,
)
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["events"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mock_meet_link() -> str:
    """Generate a realistic-looking (but fake) Google Meet URL."""
    a = secrets.token_hex(2)[:3]
    b = secrets.token_hex(2)[:4]
    c = secrets.token_hex(2)[:3]
    return f"https://meet.google.com/{a}-{b}-{c}"


# ── NLP Parse ─────────────────────────────────────────────────────────────────

@router.post("/schedule/parse")
async def schedule_parse(payload: ParseRequest):
    """
    Convert free-text scheduling intent to structured event data via GPT-4.1.
    Looks up the mentioned client name in MongoDB to attach client_id/email.
    """
    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="LLM key not configured")

    try:
        parsed = await ai_service.parse_schedule(payload.text, payload.default_tz)
    except Exception as exc:
        logger.error("schedule/parse failed: %s", exc)
        raise HTTPException(status_code=400, detail=f"Could not parse: {exc}")

    # Match client by name (case-insensitive prefix match)
    client_id = None
    client_email = ""
    if parsed.get("client_name"):
        m = await db.clients.find_one(
            {
                "name": {
                    "$regex": f"^{re.escape(parsed['client_name'])}",
                    "$options": "i",
                }
            },
            {"_id": 0},
        )
        if m:
            client_id = m["id"]
            client_email = m.get("email", "")
            parsed["client_name"] = m["name"]

    parsed["client_id"] = client_id
    parsed["client_email"] = client_email
    return parsed


# ── Events CRUD ────────────────────────────────────────────────────────────────

@router.post("/events", response_model=EventOut)
async def create_event(payload: EventCreate, background_tasks: BackgroundTasks):
    # Resolve client details
    client_name = ""
    client_email = payload.client_email or ""
    if payload.client_id:
        c = await db.clients.find_one({"id": payload.client_id}, {"_id": 0})
        if c:
            client_name = c["name"]
            if not client_email:
                client_email = c.get("email", "")

    reminders = reminders_for(payload.start_iso)

    # Compute end time and timezone for Google Calendar
    try:
        start_dt = date_parser.isoparse(payload.start_iso)
        end_iso = (start_dt + timedelta(minutes=payload.duration_minutes)).isoformat()
        tz = start_dt.tzinfo.tzname(start_dt) if start_dt.tzinfo else "Asia/Kolkata"
        if not tz or tz.startswith("UTC"):
            tz = "Asia/Kolkata"
    except Exception:
        end_iso = payload.start_iso
        tz = "Asia/Kolkata"

    # Try to create a real Google Calendar event + Meet link
    google_event_id = ""
    meet_link = ""
    html_link = ""
    if google_cal._is_configured() and payload.mode != "personal":
        gres = google_cal.create_meeting(
            summary=payload.title.strip(),
            description=(payload.notes or ""),
            start_iso=payload.start_iso,
            end_iso=end_iso,
            timezone=tz,
            attendee_emails=[client_email] if client_email else [],
            with_meet=payload.mode in ("design_call", "measurement_call"),
        )
        if gres.get("ok"):
            google_event_id = gres.get("event_id", "")
            meet_link = gres.get("meet_link", "")
            html_link = gres.get("html_link", "")

    if not meet_link:
        meet_link = _mock_meet_link()

    doc = {
        "id": str(uuid.uuid4()),
        "title": payload.title.strip(),
        "mode": payload.mode,
        "start_iso": payload.start_iso,
        "duration_minutes": payload.duration_minutes,
        "client_id": payload.client_id,
        "client_name": client_name,
        "client_email": client_email,
        "notes": payload.notes or "",
        "meet_link": meet_link,
        "google_event_id": google_event_id,
        "google_html_link": html_link,
        "reminders": reminders,
        "created_at": _now_iso(),
    }
    await db.events.insert_one(doc)

    # Schedule email reminders (morning-of / 30 min before / at start)
    schedule_event_reminders(doc["id"], payload.start_iso)

    # Send immediate "scheduled" notification email
    try:
        dt = date_parser.isoparse(payload.start_iso)
        when_human = dt.strftime("%A, %d %b %Y · %I:%M %p %Z")
    except Exception:
        when_human = payload.start_iso

    invite_html = meeting_html(doc["title"], when_human, meet_link, doc["notes"])
    recipients: set[str] = set()
    if client_email and payload.mode != "personal":
        recipients.add(client_email)
    if settings.gmail_user:
        recipients.add(settings.gmail_user)
    for r in recipients:
        background_tasks.add_task(
            send_email_sync, r, f"{doc['title']} — Scheduled", invite_html
        )

    doc.pop("_id", None)
    return EventOut(**doc)


@router.get("/events", response_model=List[EventOut])
async def list_events(
    from_iso: Optional[str] = None,
    to_iso: Optional[str] = None,
):
    q: dict = {}
    if from_iso and to_iso:
        q = {"start_iso": {"$gte": from_iso, "$lte": to_iso}}
    cursor = db.events.find(q, {"_id": 0}).sort("start_iso", 1)
    return [EventOut(**d) async for d in cursor]


@router.delete("/events/{event_id}")
async def delete_event(event_id: str):
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if ev and ev.get("google_event_id"):
        google_cal.delete_event(ev["google_event_id"])
    cancel_event_reminders(event_id)
    await db.events.delete_one({"id": event_id})
    return {"ok": True}


@router.put("/events/{event_id}", response_model=EventOut)
async def reschedule_event(
    event_id: str,
    payload: EventReschedule,
    background_tasks: BackgroundTasks,
):
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    reminders = reminders_for(payload.start_iso)

    # Update Google Calendar event time
    try:
        new_start = date_parser.isoparse(payload.start_iso)
        new_end = (
            new_start + timedelta(minutes=ev.get("duration_minutes", 30))
        ).isoformat()
        tz = new_start.tzinfo.tzname(new_start) if new_start.tzinfo else "Asia/Kolkata"
        if not tz or tz.startswith("UTC"):
            tz = "Asia/Kolkata"
    except Exception:
        new_end = payload.start_iso
        tz = "Asia/Kolkata"

    if ev.get("google_event_id"):
        google_cal.update_event_time(ev["google_event_id"], payload.start_iso, new_end, tz)

    await db.events.update_one(
        {"id": event_id},
        {"$set": {"start_iso": payload.start_iso, "reminders": reminders}},
    )
    ev["start_iso"] = payload.start_iso
    ev["reminders"] = reminders

    # Re-schedule reminder jobs
    schedule_event_reminders(event_id, payload.start_iso)

    # Send reschedule notification emails
    try:
        dt = date_parser.isoparse(payload.start_iso)
        when_human = dt.strftime("%A, %d %b %Y · %I:%M %p %Z")
    except Exception:
        when_human = payload.start_iso

    notes_with_tag = (ev.get("notes", "") or "") + " (Rescheduled)"
    html = meeting_html(ev["title"], when_human, ev.get("meet_link", ""), notes_with_tag)
    recipients: set[str] = set()
    if ev.get("client_email") and ev.get("mode") != "personal":
        recipients.add(ev["client_email"])
    if settings.gmail_user:
        recipients.add(settings.gmail_user)
    for r in recipients:
        background_tasks.add_task(
            send_email_sync, r, f"{ev['title']} — Rescheduled", html
        )

    return EventOut(**ev)
