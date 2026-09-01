"""
app/routes/clients.py — Client CRUD routes with Role-Based Access Control.

Role Enforcement:
  - Owner: Full access to all clients, bundles with invoices, creation, deletion.
  - Employee:
      - Can ONLY list/view/edit clients in their assigned_client_ids.
      - Accessing unassigned clients raises 403 Forbidden.
      - Invoice / financial data is NEVER returned in client bundles for employees.
      - Client creation and deletion are forbidden for employees (403 Forbidden).
      - Automatically logs activity on client view / edit.

Endpoints:
  GET    /api/clients
  POST   /api/clients
  GET    /api/clients/{client_id}
  PUT    /api/clients/{client_id}
  DELETE /api/clients/{client_id}
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import AuthContext, get_current_auth, require_owner
from app.database import db
from app.models.client import ClientCreate, ClientOut, ClientUpdate
from app.services.activity_logger import log_employee_activity

logger = logging.getLogger(__name__)
router = APIRouter(tags=["clients"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/clients", response_model=List[ClientOut])
async def list_clients(auth: AuthContext = Depends(get_current_auth)):
    """
    Return clients sorted by creation date (newest first).
    - If Owner: returns all clients.
    - If Employee: returns ONLY clients in assigned_client_ids.
    """
    query = {}
    if auth.is_employee:
        assigned_ids = auth.assigned_client_ids or []
        query = {"id": {"$in": assigned_ids}}

    cursor = db.clients.find(query, {"_id": 0}).sort("created_at", -1)
    return [ClientOut(**d) async for d in cursor]


@router.post("/clients", response_model=ClientOut)
async def create_client(
    payload: ClientCreate,
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Create a new client.
    Only Owner is permitted to create new clients.
    """
    if auth.is_employee:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only owners can create new clients.",
        )

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
async def get_client(
    client_id: str,
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Return a client bundle.
    - If Employee:
        - 403 Forbidden if not assigned to this client.
        - Invoices and payments are completely omitted.
        - View action is automatically logged in ActivityLog.
    - If Owner:
        - Returns full bundle with client, design PDFs, and invoice.
    """
    if not auth.can_access_client(client_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You are not assigned to this client.",
        )

    c = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    pdfs_cursor = db.pdfs.find(
        {"client_id": client_id},
        {"_id": 0, "data_base64": 0},
    ).sort("uploaded_at", -1)
    pdfs = [d async for d in pdfs_cursor]

    if auth.is_employee:
        # Automatic activity logging
        await log_employee_activity(
            auth=auth,
            entity_type="client",
            entity_id=client_id,
            client_id=client_id,
            action=f"viewed measurements for client {c.get('name')}",
            details="Viewed client profile & measurements",
        )
        return {"client": c, "pdfs": pdfs, "invoice": None}

    inv = (
        await db.invoices.find_one({"client_id": client_id}, {"_id": 0})
        or {"client_id": client_id, "items": []}
    )

    return {"client": c, "pdfs": pdfs, "invoice": inv}


@router.put("/clients/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: str,
    payload: ClientUpdate,
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Update client details / measurements.
    - If Employee: must be assigned to client, triggers automatic ActivityLog.
    - If Owner: unrestricted.
    """
    if not auth.can_access_client(client_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You are not assigned to this client.",
        )

    update = {k: v for k, v in payload.dict().items() if v is not None}
    if not update:
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

    if auth.is_employee:
        action_desc = "edited measurements for client" if "measurements" in update else "updated client profile"
        await log_employee_activity(
            auth=auth,
            entity_type="client",
            entity_id=client_id,
            client_id=client_id,
            action=f"{action_desc} {res.get('name')}",
            details=f"Updated fields: {list(update.keys())}",
        )

    return ClientOut(**res)


@router.delete("/clients/{client_id}")
async def delete_client(
    client_id: str,
    auth: AuthContext = Depends(require_owner),
):
    """
    Delete a client and all associated data (Owner only).
    """
    await db.clients.delete_one({"id": client_id})
    await db.pdfs.delete_many({"client_id": client_id})
    await db.invoices.delete_many({"client_id": client_id})
    await db.share_tokens.delete_many({"client_id": client_id})
    return {"ok": True}
