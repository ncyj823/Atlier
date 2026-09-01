"""
app/routes/projects.py — Project CRUD, canvas save/load, and client projects list.

Role Enforcement:
  - Owner: Full access to all projects, financial fields (total_amount, paid_amount), canvas.
  - Employee:
      - Can ONLY list/view/edit projects for clients in their assigned_client_ids.
      - Accessing unassigned projects raises 403 Forbidden.
      - Financial fields (total_amount, paid_amount) are stripped/hidden from responses.
      - Project deletion is restricted to Owner (403 Forbidden for employees).
      - Automatically logs activity on project view / canvas edit.

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
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import AuthContext, get_current_auth, require_owner
from app.database import db
from app.models.project import CanvasSave, ProjectCreate, ProjectUpdate
from app.services.activity_logger import log_employee_activity
from app.services.scheduler import reminders_for, schedule_event_reminders

logger = logging.getLogger(__name__)
router = APIRouter(tags=["projects"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_project_for_employee(project_dict: dict) -> dict:
    """Strip financial information for employee view."""
    p = project_dict.copy()
    p.pop("total_amount", None)
    p.pop("paid_amount", None)
    return p


async def _ensure_sending_event(
    project_id: str, title: str, client_id: Optional[str], deadline: str
) -> None:
    """Create or update a 'Sending Pieces' calendar event 2 days before the deadline."""
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
async def list_projects(auth: AuthContext = Depends(get_current_auth)):
    """
    Return projects sorted by deadline asc (no deadline last).
    - If Employee: returns only projects for assigned clients, strips financial fields.
    - If Owner: returns all projects with full financial info.
    """
    query = {}
    if auth.is_employee:
        assigned_ids = auth.assigned_client_ids or []
        query = {"client_id": {"$in": assigned_ids}}

    cursor = db.projects.find(query, {"_id": 0}).sort("deadline", 1)
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

    if auth.is_employee:
        items = [_sanitize_project_for_employee(p) for p in items]

    items.sort(key=lambda p: (p.get("deadline") or "9999-12-31", p.get("created_at", "")))
    return items


@router.post("/projects")
async def create_project(
    payload: ProjectCreate,
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Create a project.
    Only Owner is permitted to create new projects.
    """
    if auth.is_employee:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only owners can create new projects.",
        )

    c = await db.clients.find_one({"id": payload.client_id}, {"_id": 0, "id": 1, "name": 1})
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

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

    await db.canvases.insert_one(
        {
            "project_id": doc["id"],
            "gender": payload.mannequin_gender or "female",
            "strokes": [],
            "updated_at": _now_iso(),
        }
    )

    if payload.deadline:
        await _ensure_sending_event(doc["id"], doc["title"], payload.client_id, payload.deadline)

    doc.pop("_id", None)
    doc["client_name"] = c["name"]
    return doc


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Get single project bundle.
    - If Employee: must be assigned to project's client, financial fields stripped, logs activity.
    - If Owner: full access.
    """
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    client_id = p.get("client_id")
    if not auth.can_access_client(client_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You are not assigned to this project's client.",
        )

    c = await db.clients.find_one({"id": client_id}, {"_id": 0})
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

    if auth.is_employee:
        await log_employee_activity(
            auth=auth,
            entity_type="project",
            entity_id=project_id,
            client_id=client_id,
            project_id=project_id,
            action=f"viewed project {p.get('title')}",
            details=f"Viewed project details (Client: {(c or {}).get('name', '')})",
        )
        p = _sanitize_project_for_employee(p)

    return {"project": p, "client": c, "pdfs": pdfs, "canvas": canvas}


@router.put("/projects/{project_id}")
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Update project details.
    - If Employee: must be assigned to client, cannot modify total_amount/paid_amount, logs activity.
    - If Owner: full access.
    """
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    client_id = p.get("client_id")
    if not auth.can_access_client(client_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You are not assigned to this project's client.",
        )

    update = {k: v for k, v in payload.dict().items() if v is not None}
    if auth.is_employee:
        # Ignore financial fields if submitted by an employee
        update.pop("total_amount", None)
        update.pop("paid_amount", None)

    if not update:
        return _sanitize_project_for_employee(p) if auth.is_employee else p

    update["updated_at"] = _now_iso()
    res = await db.projects.find_one_and_update(
        {"id": project_id},
        {"$set": update},
        projection={"_id": 0},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Project not found")

    if "deadline" in update and update["deadline"]:
        await _ensure_sending_event(
            project_id, res.get("title", "Project"), res.get("client_id"), update["deadline"]
        )

    if auth.is_employee:
        await log_employee_activity(
            auth=auth,
            entity_type="project",
            entity_id=project_id,
            client_id=client_id,
            project_id=project_id,
            action=f"updated project {res.get('title')}",
            details=f"Updated project fields: {list(update.keys())}",
        )
        return _sanitize_project_for_employee(res)

    return res


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    auth: AuthContext = Depends(require_owner),
):
    """Delete a project (Owner only)."""
    await db.projects.delete_one({"id": project_id})
    await db.pdfs.delete_many({"project_id": project_id})
    await db.canvases.delete_many({"project_id": project_id})
    return {"ok": True}


# ── Canvas ─────────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/canvas")
async def get_canvas(
    project_id: str,
    auth: AuthContext = Depends(get_current_auth),
):
    p = await db.projects.find_one({"id": project_id}, {"_id": 0, "client_id": 1})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    if not auth.can_access_client(p.get("client_id")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You are not assigned to this project's client.",
        )

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
async def save_canvas(
    project_id: str,
    payload: CanvasSave,
    auth: AuthContext = Depends(get_current_auth),
):
    p = await db.projects.find_one({"id": project_id}, {"_id": 0, "client_id": 1, "title": 1})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    if not auth.can_access_client(p.get("client_id")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You are not assigned to this project's client.",
        )

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

    if auth.is_employee:
        await log_employee_activity(
            auth=auth,
            entity_type="canvas",
            entity_id=project_id,
            client_id=p.get("client_id"),
            project_id=project_id,
            action=f"saved canvas sketch for {p.get('title')}",
            details="Saved mannequin canvas strokes",
        )

    return {"ok": True}


# ── Client projects ────────────────────────────────────────────────────────────

@router.get("/clients/{client_id}/projects")
async def client_projects(
    client_id: str,
    auth: AuthContext = Depends(get_current_auth),
):
    if not auth.can_access_client(client_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You are not assigned to this client.",
        )

    cursor = db.projects.find({"client_id": client_id}, {"_id": 0}).sort("deadline", 1)
    items = [d async for d in cursor]
    if auth.is_employee:
        items = [_sanitize_project_for_employee(p) for p in items]
    items.sort(key=lambda p: (p.get("deadline") or "9999-12-31", p.get("created_at", "")))
    return items
