"""
app/services/google_cal.py — Google Calendar + Meet integration.

Uses a stored OAuth2 refresh token to mint access tokens on demand and call
calendar.events.insert with a Meet conferenceData.createRequest so each event
gets a real meet.google.com link.

All credentials come from environment variables via settings. If any of
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, or GOOGLE_REFRESH_TOKEN is absent,
all functions silently return failure dicts — the app falls back to mock links.
"""
import uuid
import logging
from typing import List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def _is_configured() -> bool:
    return settings.google_configured


def _service():
    """Build and return an authenticated Google Calendar service, or None."""
    if not _is_configured():
        return None
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=settings.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=SCOPES,
        )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as exc:
        logger.error("Google Calendar service build failed: %s", exc)
        return None


def create_meeting(
    summary: str,
    description: str,
    start_iso: str,
    end_iso: str,
    timezone: str = "Asia/Kolkata",
    attendee_emails: Optional[List[str]] = None,
    with_meet: bool = True,
) -> dict:
    """
    Create a Google Calendar event with an optional Meet link.

    Returns:
        {ok: True, event_id, html_link, meet_link} on success
        {ok: False, error: str} on failure or when not configured
    """
    svc = _service()
    if not svc:
        return {"ok": False, "error": "google not configured"}

    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso, "timeZone": timezone},
        "end": {"dateTime": end_iso, "timeZone": timezone},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60 * 24},
                {"method": "popup", "minutes": 60},
                {"method": "popup", "minutes": 30},
                {"method": "email", "minutes": 30},
            ],
        },
    }
    if attendee_emails:
        body["attendees"] = [{"email": e} for e in attendee_emails if e]
    if with_meet:
        body["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }

    try:
        from googleapiclient.errors import HttpError

        ev = (
            svc.events()
            .insert(
                calendarId=settings.google_calendar_id,
                body=body,
                conferenceDataVersion=1 if with_meet else 0,
                sendUpdates="all" if attendee_emails else "none",
            )
            .execute()
        )
        meet_link = ""
        for ep in (ev.get("conferenceData") or {}).get("entryPoints", []):
            if ep.get("entryPointType") == "video":
                meet_link = ep.get("uri", "")
                break
        return {
            "ok": True,
            "event_id": ev.get("id"),
            "html_link": ev.get("htmlLink", ""),
            "meet_link": meet_link,
        }
    except Exception as exc:
        logger.error("Google Calendar create_meeting failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def update_event_time(
    event_id: str,
    start_iso: str,
    end_iso: str,
    timezone: str = "Asia/Kolkata",
) -> dict:
    """Patch the start/end time of an existing calendar event."""
    svc = _service()
    if not svc or not event_id:
        return {"ok": False, "error": "google not configured or missing event_id"}
    try:
        ev = (
            svc.events()
            .patch(
                calendarId=settings.google_calendar_id,
                eventId=event_id,
                body={
                    "start": {"dateTime": start_iso, "timeZone": timezone},
                    "end": {"dateTime": end_iso, "timeZone": timezone},
                },
                sendUpdates="all",
            )
            .execute()
        )
        return {"ok": True, "event_id": ev.get("id")}
    except Exception as exc:
        logger.error("Google Calendar update_event_time failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def delete_event(event_id: str) -> dict:
    """Delete a calendar event. Silently returns {ok: False} if not configured."""
    svc = _service()
    if not svc or not event_id:
        return {"ok": False}
    try:
        svc.events().delete(
            calendarId=settings.google_calendar_id,
            eventId=event_id,
            sendUpdates="all",
        ).execute()
        return {"ok": True}
    except Exception as exc:
        logger.error("Google Calendar delete_event failed: %s", exc)
        return {"ok": False, "error": str(exc)}
