import html as html_lib
import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.config import settings
from app.database import db

logger = logging.getLogger(__name__)
auth_router = APIRouter(tags=["share"])
public_router = APIRouter(tags=["share"])
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@auth_router.post("/clients/{client_id}/share")
async def create_share_link(client_id: str):
    """
    Create a share link for a client profile. If one already exists, reuse it.
    Returns {token, url}.
    """
    c = await db.clients.find_one({"id": client_id}, {"_id": 0, "id": 1})
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    existing = await db.share_tokens.find_one({"client_id": client_id}, {"_id": 0})
    if existing:
        token = existing["token"]
    else:
        token = secrets.token_urlsafe(16)
        await db.share_tokens.insert_one(
            {"token": token, "client_id": client_id, "created_at": _now_iso()}
        )

    return {"token": token, "url": f"{settings.public_base_url}/api/share/{token}"}


@public_router.get("/share/{token}", response_class=HTMLResponse)
async def public_share(token: str):
    """
    Public read-only HTML page for a client profile.
    No auth required — the token is the only gate.
    All values from the database are HTML-escaped before rendering.
    """
    rec = await db.share_tokens.find_one({"token": token}, {"_id": 0})
    if not rec:
        return HTMLResponse(
            "<h2 style='font-family:Georgia;margin:40px'>Link not found.</h2>",
            status_code=404,
        )

    cid = rec["client_id"]
    c = await db.clients.find_one({"id": cid}, {"_id": 0})
    if not c:
        return HTMLResponse(
            "<h2 style='font-family:Georgia;margin:40px'>Client not found.</h2>",
            status_code=404,
        )

    pdfs_cursor = db.pdfs.find(
        {"client_id": cid}, {"_id": 0, "data_base64": 0}
    ).sort("uploaded_at", -1)
    pdfs = [d async for d in pdfs_cursor]
    inv = await db.invoices.find_one({"client_id": cid}, {"_id": 0}) or {"items": []}

    esc = html_lib.escape

    measurements_html = "".join(
        f"<tr>"
        f"<td style='padding:6px 12px 6px 0;color:#6B6761;text-transform:uppercase;"
        f"font-size:11px;letter-spacing:.1em'>{esc(str(k))}</td>"
        f"<td style='padding:6px 0'>{esc(str(v))}</td>"
        f"</tr>"
        for k, v in (c.get("measurements") or {}).items()
    ) or "<tr><td style='color:#6B6761'>No measurements on file.</td></tr>"

    pdfs_html = "".join(
        f"<li style='padding:8px 0;border-bottom:1px solid #EAE5DA'>"
        f"{esc(p['name'])} "
        f"<span style='color:#6B6761;font-size:12px'>· {esc(p['uploaded_at'][:10])}</span>"
        f"</li>"
        for p in pdfs
    ) or "<li style='color:#6B6761'>No design sheets yet.</li>"

    inv_items = inv.get("items", [])
    inv_rows = "".join(
        f"<tr>"
        f"<td style='padding:10px 0;border-bottom:1px solid #EAE5DA'>{esc(it['description'])}</td>"
        f"<td style='padding:10px 0;border-bottom:1px solid #EAE5DA;text-align:right'>₹{it['amount']:.2f}</td>"
        f"<td style='padding:10px 0;border-bottom:1px solid #EAE5DA;text-align:right;"
        f"text-transform:uppercase;font-size:11px;letter-spacing:.1em;"
        f"color:{'#5C6B5D' if it['status'] == 'cleared' else '#B38A58'}'>"
        f"{esc(it['status'])}</td>"
        f"</tr>"
        for it in inv_items
    ) or "<tr><td style='color:#6B6761;padding:10px 0'>No invoice items.</td></tr>"

    client_name = esc(c["name"])
    client_email = esc(c.get("email", ""))
    client_whatsapp = esc(c["whatsapp"]) if c.get("whatsapp") else ""

    return HTMLResponse(f"""<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{client_name} — Atelier</title>
<style>
body{{margin:0;background:#FDFBF7;color:#1A1918;font-family:Arial,sans-serif}}
.wrap{{max-width:680px;margin:0 auto;padding:32px 24px}}
h1{{font-family:Georgia,serif;font-weight:400;font-size:36px;margin:0 0 8px}}
h2{{font-family:Georgia,serif;font-weight:400;font-size:20px;margin:32px 0 12px}}
.kicker{{letter-spacing:.2em;text-transform:uppercase;color:#A3523B;font-size:12px}}
</style>
</head><body><div class="wrap">
<p class="kicker">Atelier · Client Profile</p>
<h1>{client_name}</h1>
<p style="color:#6B6761">{client_email} {("· " + client_whatsapp) if client_whatsapp else ""}</p>
<h2>Measurements</h2><table>{measurements_html}</table>
<h2>Design Sheets</h2><ul style="list-style:none;padding:0;margin:0">{pdfs_html}</ul>
<h2>Invoice</h2><table style="width:100%;border-collapse:collapse">{inv_rows}</table>
<p style="color:#6B6761;font-size:12px;margin-top:48px">Shared via Atelier — read-only.</p>
</div></body></html>""")
