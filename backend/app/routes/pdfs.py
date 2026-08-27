"""
app/routes/pdfs.py — PDF upload/download/delete for clients and projects.

Endpoints:
  POST   /api/clients/{client_id}/pdfs
  GET    /api/clients/{client_id}/pdfs/{pdf_id}
  DELETE /api/clients/{client_id}/pdfs/{pdf_id}
  POST   /api/projects/{project_id}/pdfs
  DELETE /api/projects/{project_id}/pdfs/{pdf_id}
"""
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.database import db
from app.models.common import PDFUpload

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pdfs"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Client PDFs ────────────────────────────────────────────────────────────────

@router.post("/clients/{client_id}/pdfs")
async def upload_client_pdf(client_id: str, payload: PDFUpload):
    client_doc = await db.clients.find_one({"id": client_id}, {"_id": 0, "id": 1})
    if not client_doc:
        raise HTTPException(status_code=404, detail="Client not found")

    doc = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "name": payload.name,
        "data_base64": payload.data_base64,
        "size_bytes": len(payload.data_base64),
        "uploaded_at": _now_iso(),
    }
    await db.pdfs.insert_one(doc)
    return {
        "id": doc["id"],
        "name": doc["name"],
        "uploaded_at": doc["uploaded_at"],
        "size_bytes": doc["size_bytes"],
    }


@router.get("/clients/{client_id}/pdfs/{pdf_id}")
async def get_client_pdf(client_id: str, pdf_id: str):
    p = await db.pdfs.find_one({"id": pdf_id, "client_id": client_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="PDF not found")
    return p


@router.delete("/clients/{client_id}/pdfs/{pdf_id}")
async def delete_client_pdf(client_id: str, pdf_id: str):
    await db.pdfs.delete_one({"id": pdf_id, "client_id": client_id})
    return {"ok": True}


# ── Project PDFs ───────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/pdfs")
async def upload_project_pdf(project_id: str, payload: PDFUpload):
    p = await db.projects.find_one({"id": project_id}, {"_id": 0, "id": 1})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    doc = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "name": payload.name,
        "data_base64": payload.data_base64,
        "size_bytes": len(payload.data_base64),
        "uploaded_at": _now_iso(),
    }
    await db.pdfs.insert_one(doc)
    return {
        "id": doc["id"],
        "name": doc["name"],
        "uploaded_at": doc["uploaded_at"],
        "size_bytes": doc["size_bytes"],
    }


@router.delete("/projects/{project_id}/pdfs/{pdf_id}")
async def delete_project_pdf(project_id: str, pdf_id: str):
    await db.pdfs.delete_one({"id": pdf_id, "project_id": project_id})
    return {"ok": True}
