"""
app/routes/invoices.py — Invoice item CRUD routes (Owner Only).

All invoice and payment management is restricted strictly to the Owner tier.
Employees receive 403 Forbidden.

Endpoints:
  POST   /api/clients/{client_id}/invoices/items
  PUT    /api/clients/{client_id}/invoices/items/{item_id}
  DELETE /api/clients/{client_id}/invoices/items/{item_id}
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.auth import AuthContext, require_owner
from app.database import db
from app.models.invoice import InvoiceItem, InvoiceItemCreate
from app.services.email_service import invoice_html, send_email_sync

logger = logging.getLogger(__name__)
router = APIRouter(tags=["invoices"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _send_invoice_email_if_possible(
    client_id: str, background_tasks: BackgroundTasks
) -> None:
    """Fire-and-forget invoice email to the client if they have an email address."""
    c = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not c or not c.get("email"):
        return
    inv = (
        await db.invoices.find_one({"client_id": client_id}, {"_id": 0})
        or {"items": []}
    )
    html = invoice_html(c["name"], inv.get("items", []))
    background_tasks.add_task(
        send_email_sync,
        c["email"],
        f"Invoice update — {c['name']}",
        html,
    )


@router.post("/clients/{client_id}/invoices/items")
async def add_invoice_item(
    client_id: str,
    payload: InvoiceItemCreate,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_owner),
):
    item = InvoiceItem(**payload.dict()).dict()
    await db.invoices.update_one(
        {"client_id": client_id},
        {
            "$push": {"items": item},
            "$setOnInsert": {"client_id": client_id, "created_at": _now_iso()},
        },
        upsert=True,
    )
    await _send_invoice_email_if_possible(client_id, background_tasks)
    return item


@router.put("/clients/{client_id}/invoices/items/{item_id}")
async def update_invoice_item(
    client_id: str,
    item_id: str,
    payload: InvoiceItemCreate,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_owner),
):
    res = await db.invoices.update_one(
        {"client_id": client_id, "items.id": item_id},
        {
            "$set": {
                "items.$.description": payload.description,
                "items.$.amount": payload.amount,
                "items.$.status": payload.status,
            }
        },
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    await _send_invoice_email_if_possible(client_id, background_tasks)
    return {"ok": True}


@router.delete("/clients/{client_id}/invoices/items/{item_id}")
async def delete_invoice_item(
    client_id: str,
    item_id: str,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_owner),
):
    await db.invoices.update_one(
        {"client_id": client_id},
        {"$pull": {"items": {"id": item_id}}},
    )
    await _send_invoice_email_if_possible(client_id, background_tasks)
    return {"ok": True}
