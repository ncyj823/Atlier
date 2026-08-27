"""
app/routes/projects.py — Project CRUD, canvas save/load, and client projects list.

Endpoints:
  GET    /api/projects
  POST   /api/projects
  GET    /api/projects/{project_id}
  PUT    /api/projects/{project_id}
  DELETE /api/projects/{project_id}
  GET    /api/projects/{project_id}/canvas
  PUT    /api/projects/{project_id}/canvas
  GET    /api/clients/{client_id}/projects
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytz
from dateutil import parser as date_parser
from fastapi import APIRouter, HTTPException

from app.database import db
from app.models.project import CanvasSave, ProjectCreate, ProjectUpdate
from app.services import google_cal
from app.services.scheduler import reminders_for, schedule_event_reminders

logger = logging.getLogger(__name__)
router = APIRouter(tags=["projects"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_sending_event(
    project_id: str, title: str, client_id: Optional[str], deadline: str
) -> None:
    """
    Create or update a 'Sending Pieces' calendar event 2 days before the
    project deadline. If one already exists for this project, update it.

    NOTE: pytz zones must be attached via localize(), not replace(tzinfo=...).
    replace() pins the zone's first historical UTC offset (~+5:53 LMT for
    Asia/Kolkata) instead of the current +5:30, silently scheduling events
    ~23 minutes off from the intended local time.
    """
    try:
        ist = pytz.timezone("Asia/Kolkata")
        if len(deadline) == 10:
            dl = ist.localize(datetime.fromisoformat(deadline + "T10:00:00"))
        else:
            dl = date_parser.isoparse(deadline)
            if dl.tzinfo is None:
                dl = ist.localize(dl)
        start = dl - timedelta(days=2)
    except Exception as exc:
        logger.error("_ensure_sending_event date parse failed: %s", exc)
        return

    client_name = ""
    if client_id:
        c = await db.clients.find_one({"id": client_id}, {"_id": 0, "name": 1})
        if c:
            client_name = c["name"]

    ev_title = f"Send pieces — {title}"
    existing = await db.events.find_one(
        {"project_id": project_id, "auto_kind": "sending_pieces"}, {"_id": 0}
    )
    if existing:
        await db.events.update_one(
            {"id": existing["id"]},
            {
                "$set": {
                    "start_iso": start.isoformat(),
                    "title": ev_title,
                    "client_name": client_name,
                }
            },
        )
        schedule_event_reminders(existing["id"], start.isoformat())
        return

    new_id = str(uuid.uuid4())
    await db.events.insert_one(
        {
            "id": new_id,
            "title": ev_title,
            "mode": "sending_pieces",
            "start_iso": start.isoformat(),
            "duration_minutes": 60,
            "client_id": client_id,
            "client_name": client_name,
            "client_email": "",
            "notes": "Auto-scheduled 2 days before project deadline.",
            "meet_link": "",
            "google_event_id": "",
            "google_html_link": "",
            "reminders": reminders_for(start.isoformat()),
            "auto_kind": "sending_pieces",
            "project_id": project_id,
            "created_at": _now_iso(),
        }
    )
    schedule_event_reminders(new_id, start.isoformat())


# ── Project CRUD ───────────────────────────────────────────────────────────────

@router.get("/projects")
async def list_projects():
    """Return all projects with client_name attached, sorted by deadline asc (no deadline last)."""
    cursor = db.projects.find({}, {"_id": 0}).sort("deadline", 1)
    items = [d async for d in cursor]

    client_ids = list({p.get("client_id") for p in items if p.get("client_id")})
    clients_map: dict = {}
    if client_ids:
        async for c in db.clients.find(
            {"id": {"$in": client_ids}}, {"_id": 0, "id": 1, "name": 1}
        ):
            clients_map[c["id"]] = c["name"]

    for p in items:
        p["client_name"] = clients_map.get(p.get("client_id"), "")

    # Items with no deadline go to the end
    items.sort(key=lambda p: (p.get("deadline") or "9999-12-31", p.get("created_at", "")))
    return items


@router.post("/projects")
async def create_project(payload: ProjectCreate):
    c = await db.clients.find_one({"id": payload.client_id}, {"_id": 0, "id": 1, "name": 1})
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    # Sequential ATL-NNNN UID via atomic counter document
    counter = await db.counters.find_one_and_update(
        {"_id": "project"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = counter.get("seq", 1)
    uid = f"ATL-{seq:04d}"

    doc = {
        "id": str(uuid.uuid4()),
        "uid": uid,
        "client_id": payload.client_id,
        "title": payload.title.strip(),
        "delivery_location": payload.delivery_location or "",
        "deadline": payload.deadline,
        "description": payload.description or "",
        "total_amount": float(payload.total_amount or 0),
        "paid_amount": float(payload.paid_amount or 0),
        "status": payload.status or "ongoing",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.projects.insert_one(doc)

    # Auto-create a canvas for the mannequin sketch
    await db.canvases.insert_one(
        {
            "project_id": doc["id"],
            "gender": payload.mannequin_gender or "female",
            "strokes": [],
            "updated_at": _now_iso(),
        }
    )

    # Auto-create "Sending Pieces" event 2 days before deadline
    if payload.deadline:
        await _ensure_sending_event(doc["id"], doc["title"], payload.client_id, payload.deadline)

    doc.pop("_id", None)
    doc["client_name"] = c["name"]
    return doc


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    c = await db.clients.find_one({"id": p.get("client_id")}, {"_id": 0})
    pdfs_cursor = db.pdfs.find(
        {"project_id": project_id}, {"_id": 0, "data_base64": 0}
    ).sort("uploaded_at", -1)
    pdfs = [d async for d in pdfs_cursor]
    canvas = await db.canvases.find_one({"project_id": project_id}, {"_id": 0}) or {
        "project_id": project_id,
        "gender": "female",
        "strokes": [],
        "updated_at": _now_iso(),
    }
    p["client_name"] = (c or {}).get("name", "")
    return {"project": p, "client": c, "pdfs": pdfs, "canvas": canvas}


@router.put("/projects/{project_id}")
async def update_project(project_id: str, payload: ProjectUpdate):
    update = {k: v for k, v in payload.dict().items() if v is not None}
    if not update:
        return {"ok": True}
    update["updated_at"] = _now_iso()
    res = await db.projects.find_one_and_update(
        {"id": project_id},
        {"$set": update},
        projection={"_id": 0},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Project not found")
    # If deadline changed, refresh the auto sending event
    if "deadline" in update and update["deadline"]:
        await _ensure_sending_event(
            project_id, res.get("title", "Project"), res.get("client_id"), update["deadline"]
        )
    return res


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    await db.projects.delete_one({"id": project_id})
    await db.pdfs.delete_many({"project_id": project_id})
    await db.canvases.delete_many({"project_id": project_id})
    return {"ok": True}


# ── Canvas ─────────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/canvas")
async def get_canvas(project_id: str):
    canvas = await db.canvases.find_one({"project_id": project_id}, {"_id": 0})
    if not canvas:
        canvas = {
            "project_id": project_id,
            "gender": "female",
            "strokes": [],
            "updated_at": _now_iso(),
        }
        await db.canvases.insert_one(canvas.copy())
    return canvas


@router.put("/projects/{project_id}/canvas")
async def save_canvas(project_id: str, payload: CanvasSave):
    await db.canvases.update_one(
        {"project_id": project_id},
        {
            "$set": {
                "project_id": project_id,
                "gender": payload.gender,
                "strokes": payload.strokes,
                "updated_at": _now_iso(),
            }
        },
        upsert=True,
    )
    return {"ok": True}


# ── Client projects ────────────────────────────────────────────────────────────

@router.get("/clients/{client_id}/projects")
async def client_projects(client_id: str):
    cursor = db.projects.find({"client_id": client_id}, {"_id": 0}).sort("deadline", 1)
    items = [d async for d in cursor]
    items.sort(key=lambda p: (p.get("deadline") or "9999-12-31", p.get("created_at", "")))
    return items
