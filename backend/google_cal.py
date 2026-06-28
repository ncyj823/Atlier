"""Google Calendar + Meet integration. Uses a stored refresh token to mint
access tokens on demand and call calendar.events.insert with a Meet
conferenceData.createRequest so each event gets a real meet.google.com link.
"""
import os
import uuid
import logging
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN", "")
GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
]


def _is_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN)


def _service():
    if not _is_configured():
        return None
    creds = Credentials(
        token=None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def create_meeting(
    summary: str,
    description: str,
    start_iso: str,
    end_iso: str,
    timezone: str = "Asia/Kolkata",
    attendee_emails: Optional[List[str]] = None,
    with_meet: bool = True,
):
    """Returns dict with keys: ok, html_link, meet_link, event_id, error?"""
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
        ev = svc.events().insert(
            calendarId=GOOGLE_CALENDAR_ID,
            body=body,
            conferenceDataVersion=1 if with_meet else 0,
            sendUpdates="all" if attendee_emails else "none",
        ).execute()
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
    except HttpError as e:
        logger.error(f"google calendar create_meeting failed: {e}")
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.error(f"google calendar create_meeting exception: {e}")
        return {"ok": False, "error": str(e)}


def update_event_time(event_id: str, start_iso: str, end_iso: str, timezone: str = "Asia/Kolkata"):
    svc = _service()
    if not svc or not event_id:
        return {"ok": False, "error": "google not configured or missing event_id"}
    try:
        ev = svc.events().patch(
            calendarId=GOOGLE_CALENDAR_ID,
            eventId=event_id,
            body={
                "start": {"dateTime": start_iso, "timeZone": timezone},
                "end": {"dateTime": end_iso, "timeZone": timezone},
            },
            sendUpdates="all",
        ).execute()
        return {"ok": True, "event_id": ev.get("id")}
    except Exception as e:
        logger.error(f"google calendar update failed: {e}")
        return {"ok": False, "error": str(e)}


def delete_event(event_id: str):
    svc = _service()
    if not svc or not event_id:
        return {"ok": False}
    try:
        svc.events().delete(
            calendarId=GOOGLE_CALENDAR_ID,
            eventId=event_id,
            sendUpdates="all",
        ).execute()
        return {"ok": True}
    except Exception as e:
        logger.error(f"google calendar delete failed: {e}")
        return {"ok": False, "error": str(e)}
