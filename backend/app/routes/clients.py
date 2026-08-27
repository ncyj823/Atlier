"""
app/routes/clients.py — Client CRUD routes.

All routes are under /api prefix and require X-API-Key authentication
(applied at the router level in main.py).

Endpoints:
  GET    /api/clients
  POST   /api/clients
  GET    /api/clients/{client_id}
  PUT    /api/clients/{client_id}
  DELETE /api/clients/{client_id}
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException

from app.database import db
from app.models.client import ClientCreate, ClientOut, ClientUpdate

logger = logging.getLogger(__name__)
router = APIRouter(tags=["clients"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/clients", response_model=List[ClientOut])
async def list_clients():
    """Return all clients sorted by creation date (newest first)."""
    cursor = db.clients.find({}, {"_id": 0}).sort("created_at", -1)
    return [ClientOut(**d) async for d in cursor]


@router.post("/clients", response_model=ClientOut)
async def create_client(payload: ClientCreate):
    doc = {
        "id": str(uuid.uuid4()),
        "name": payload.name.strip(),
        "whatsapp": payload.whatsapp or "",
        "email": payload.email or "",
        "measurements": payload.measurements or {},
        "notes": payload.notes or "",
        "created_at": _now_iso(),
        "avatar_url": None,
    }
    await db.clients.insert_one(doc)
    doc.pop("_id", None)
    return ClientOut(**doc)


@router.get("/clients/{client_id}")
async def get_client(client_id: str):
    """
    Return a client bundle containing the client record, their PDFs (without
    binary data), and their invoice.
    """
    c = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    pdfs_cursor = db.pdfs.find(
        {"client_id": client_id},
        {"_id": 0, "data_base64": 0},
    ).sort("uploaded_at", -1)
    pdfs = [d async for d in pdfs_cursor]

    inv = (
        await db.invoices.find_one({"client_id": client_id}, {"_id": 0})
        or {"client_id": client_id, "items": []}
    )

    return {"client": c, "pdfs": pdfs, "invoice": inv}


@router.put("/clients/{client_id}", response_model=ClientOut)
async def update_client(client_id: str, payload: ClientUpdate):
    """
    Partial update — only fields explicitly set in the payload are written.
    Fields omitted from the request body are left unchanged in MongoDB.
    """
    update = {k: v for k, v in payload.dict().items() if v is not None}
    if not update:
        # Nothing to change — return current record
        c = await db.clients.find_one({"id": client_id}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Client not found")
        return ClientOut(**c)

    res = await db.clients.find_one_and_update(
        {"id": client_id},
        {"$set": update},
        projection={"_id": 0},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Client not found")
    return ClientOut(**res)


@router.delete("/clients/{client_id}")
async def delete_client(client_id: str):
    """
    Delete a client and all associated data:
    PDFs, invoices, and share tokens.
    """
    await db.clients.delete_one({"id": client_id})
    await db.pdfs.delete_many({"client_id": client_id})
    await db.invoices.delete_many({"client_id": client_id})
    await db.share_tokens.delete_many({"client_id": client_id})
    return {"ok": True}
