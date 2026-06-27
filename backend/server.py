import tempfile
from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import json
import logging
import uuid
import re
import secrets
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta

import pytz
from dateutil import parser as date_parser
import resend

from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai.speech_to_text import OpenAISpeechToText

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
client_mongo = AsyncIOMotorClient(mongo_url)
db = client_mongo[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '').strip()
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'Atelier <onboarding@resend.dev>')
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', '')

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============ Models ============
EVENT_MODES = ["design_call", "measurement_call", "sending_pieces", "personal"]

class ClientCreate(BaseModel):
    name: str
    whatsapp: Optional[str] = ""
    email: Optional[str] = ""
    measurements: Optional[dict] = {}
    notes: Optional[str] = ""

class ClientOut(BaseModel):
    id: str
    name: str
    whatsapp: str = ""
    email: str = ""
    measurements: dict = {}
    notes: str = ""
    created_at: str
    avatar_url: Optional[str] = None

class EventCreate(BaseModel):
    title: str
    mode: Literal["design_call", "measurement_call", "sending_pieces", "personal"]
    start_iso: str  # ISO 8601 with tz
    duration_minutes: int = 30
    client_id: Optional[str] = None
    client_email: Optional[str] = ""
    notes: Optional[str] = ""

class EventOut(BaseModel):
    id: str
    title: str
    mode: str
    start_iso: str
    duration_minutes: int
    client_id: Optional[str] = None
    client_name: Optional[str] = ""
    client_email: Optional[str] = ""
    notes: str = ""
    meet_link: str
    reminders: List[str] = []
    created_at: str

class InvoiceItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    amount: float
    status: Literal["pending", "cleared"] = "pending"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class InvoiceItemCreate(BaseModel):
    description: str
    amount: float
    status: Literal["pending", "cleared"] = "pending"

class PDFUpload(BaseModel):
    name: str
    data_base64: str  # raw base64

class ParseRequest(BaseModel):
    text: str
    default_tz: str = "Asia/Kolkata"


# ============ Helpers ============
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _mock_meet_link() -> str:
    a = secrets.token_hex(2)[:3]
    b = secrets.token_hex(2)[:4]
    c = secrets.token_hex(2)[:3]
    return f"https://meet.google.com/{a}-{b}-{c}"

def _reminders_for(start_iso: str) -> List[str]:
    try:
        dt = date_parser.isoparse(start_iso)
    except Exception:
        return []
    return [
        (dt - timedelta(days=1)).isoformat(),
        (dt - timedelta(hours=1)).isoformat(),
        (dt - timedelta(minutes=15)).isoformat(),
    ]

async def _send_email(to: str, subject: str, html: str) -> dict:
    if not to:
        return {"sent": False, "reason": "no recipient"}
    if not RESEND_API_KEY:
        logger.info(f"[MOCKED EMAIL] to={to} subject={subject}")
        return {"sent": True, "mocked": True}
    try:
        params = {"from": SENDER_EMAIL, "to": [to], "subject": subject, "html": html}
        r = resend.Emails.send(params)
        return {"sent": True, "id": r.get("id") if isinstance(r, dict) else None}
    except Exception as e:
        logger.error(f"resend send failed: {e}")
        return {"sent": False, "error": str(e)}

def _meeting_html(title: str, when_human: str, meet_link: str, notes: str = "") -> str:
    return f"""
    <div style="font-family:Georgia,serif;max-width:560px;margin:0 auto;padding:24px;background:#FDFBF7;color:#1A1918">
      <p style="letter-spacing:.2em;color:#A3523B;font-size:12px;text-transform:uppercase">Atelier</p>
      <h2 style="font-family:Georgia,serif;margin:8px 0 16px">{title}</h2>
      <p style="margin:4px 0">When: <strong>{when_human}</strong></p>
      <p style="margin:4px 0">Join: <a href="{meet_link}" style="color:#A3523B">{meet_link}</a></p>
      {f'<p style="margin-top:16px;color:#4A4845">{notes}</p>' if notes else ''}
      <hr style="border:0;border-top:1px solid #EAE5DA;margin:24px 0" />
      <p style="font-size:12px;color:#6B6761">Sent via Atelier</p>
    </div>"""

def _invoice_html(client_name: str, items: list) -> str:
    rows = ""
    total_pending = 0.0
    for it in items:
        color = "#5C6B5D" if it["status"] == "cleared" else "#B38A58"
        rows += f"""<tr><td style="padding:10px 0;border-bottom:1px solid #EAE5DA">{it["description"]}</td>
        <td style="padding:10px 0;border-bottom:1px solid #EAE5DA;text-align:right">₹{it["amount"]:.2f}</td>
        <td style="padding:10px 0;border-bottom:1px solid #EAE5DA;color:{color};text-transform:uppercase;font-size:11px;letter-spacing:.1em;text-align:right">{it["status"]}</td></tr>"""
        if it["status"] != "cleared":
            total_pending += float(it["amount"])
    return f"""
    <div style="font-family:Georgia,serif;max-width:560px;margin:0 auto;padding:24px;background:#FDFBF7;color:#1A1918">
      <p style="letter-spacing:.2em;color:#A3523B;font-size:12px;text-transform:uppercase">Atelier — Invoice update</p>
      <h2 style="margin:8px 0 16px">Hello {client_name},</h2>
      <p>Your invoice has been updated. Latest summary below.</p>
      <table style="width:100%;border-collapse:collapse;margin-top:16px;font-family:Arial,sans-serif;font-size:14px">{rows}</table>
      <p style="margin-top:16px;font-family:Arial,sans-serif">Pending balance: <strong>₹{total_pending:.2f}</strong></p>
      <hr style="border:0;border-top:1px solid #EAE5DA;margin:24px 0" />
      <p style="font-size:12px;color:#6B6761;font-family:Arial,sans-serif">Sent via Atelier</p>
    </div>"""


# ============ NLP Parse ============
NLP_SYSTEM = """You are a scheduling parser for a fashion freelancer's app. Convert the user's text into strict JSON.

Output ONLY a JSON object with these keys:
{
  "title": string,
  "mode": "design_call" | "measurement_call" | "sending_pieces" | "personal",
  "client_name": string | null,
  "start_iso": string (ISO 8601 with timezone offset),
  "duration_minutes": integer (default 30),
  "timezone": string (IANA tz, e.g. "Asia/Kolkata"),
  "notes": string
}

Rules:
- If the user says IST / India, use Asia/Kolkata.
- "coming Wednesday" / "next Wednesday" means the next upcoming Wednesday from CURRENT_DATETIME.
- Infer mode from keywords: "design"/"call" -> design_call; "measurement"/"fitting" -> measurement_call; "send"/"deliver"/"ship" -> sending_pieces; otherwise -> personal.
- start_iso must include the timezone offset (e.g. "2026-05-21T18:00:00+05:30").
- No prose, no markdown fences. Just raw JSON.
"""

def _extract_json(text: str) -> dict:
    # Strip ```json fences if any
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(m.group(0))

async def parse_with_llm(text: str, default_tz: str) -> dict:
    now_local = datetime.now(pytz.timezone(default_tz))
    sys_msg = NLP_SYSTEM.replace("CURRENT_DATETIME", now_local.strftime("%A, %Y-%m-%d %H:%M %Z"))
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"parse-{uuid.uuid4().hex[:8]}",
        system_message=sys_msg,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    resp = await chat.send_message(UserMessage(text=text))
    data = _extract_json(resp if isinstance(resp, str) else str(resp))
    # Defaults
    data.setdefault("duration_minutes", 30)
    data.setdefault("notes", "")
    if data.get("mode") not in EVENT_MODES:
        data["mode"] = "personal"
    return data


# ============ Routes ============
@api_router.get("/")
async def root():
    return {"app": "Atelier", "ok": True}


# --- Clients ---
@api_router.post("/clients", response_model=ClientOut)
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

@api_router.get("/clients", response_model=List[ClientOut])
async def list_clients():
    cursor = db.clients.find({}, {"_id": 0}).sort("created_at", -1)
    return [ClientOut(**d) async for d in cursor]

@api_router.get("/clients/{client_id}")
async def get_client(client_id: str):
    c = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Client not found")
    pdfs_cursor = db.pdfs.find({"client_id": client_id}, {"_id": 0, "data_base64": 0}).sort("uploaded_at", -1)
    pdfs = [d async for d in pdfs_cursor]
    inv = await db.invoices.find_one({"client_id": client_id}, {"_id": 0}) or {"client_id": client_id, "items": []}
    return {"client": c, "pdfs": pdfs, "invoice": inv}

@api_router.put("/clients/{client_id}", response_model=ClientOut)
async def update_client(client_id: str, payload: ClientCreate):
    update = {k: v for k, v in payload.dict().items() if v is not None}
    res = await db.clients.find_one_and_update(
        {"id": client_id}, {"$set": update}, projection={"_id": 0}, return_document=True
    )
    if not res:
        raise HTTPException(404, "Client not found")
    return ClientOut(**res)

@api_router.delete("/clients/{client_id}")
async def delete_client(client_id: str):
    await db.clients.delete_one({"id": client_id})
    await db.pdfs.delete_many({"client_id": client_id})
    await db.invoices.delete_many({"client_id": client_id})
    await db.share_tokens.delete_many({"client_id": client_id})
    return {"ok": True}


# --- PDFs ---
@api_router.post("/clients/{client_id}/pdfs")
async def upload_pdf(client_id: str, payload: PDFUpload):
    client_doc = await db.clients.find_one({"id": client_id}, {"_id": 0, "id": 1})
    if not client_doc:
        raise HTTPException(404, "Client not found")
    doc = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "name": payload.name,
        "data_base64": payload.data_base64,
        "size_bytes": len(payload.data_base64),
        "uploaded_at": _now_iso(),
    }
    await db.pdfs.insert_one(doc)
    return {"id": doc["id"], "name": doc["name"], "uploaded_at": doc["uploaded_at"], "size_bytes": doc["size_bytes"]}

@api_router.get("/clients/{client_id}/pdfs/{pdf_id}")
async def get_pdf(client_id: str, pdf_id: str):
    p = await db.pdfs.find_one({"id": pdf_id, "client_id": client_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "PDF not found")
    return p

@api_router.delete("/clients/{client_id}/pdfs/{pdf_id}")
async def delete_pdf(client_id: str, pdf_id: str):
    await db.pdfs.delete_one({"id": pdf_id, "client_id": client_id})
    return {"ok": True}


# --- Invoices ---
async def _send_invoice_email_if_possible(client_id: str, background_tasks: BackgroundTasks):
    c = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not c or not c.get("email"):
        return
    inv = await db.invoices.find_one({"client_id": client_id}, {"_id": 0}) or {"items": []}
    html = _invoice_html(c["name"], inv.get("items", []))
    background_tasks.add_task(_send_email_sync, c["email"], f"Invoice update — {c['name']}", html)

def _send_email_sync(to, subject, html):
    import asyncio
    asyncio.run(_send_email(to, subject, html))

@api_router.post("/clients/{client_id}/invoices/items")
async def add_invoice_item(client_id: str, payload: InvoiceItemCreate, background_tasks: BackgroundTasks):
    item = InvoiceItem(**payload.dict()).dict()
    await db.invoices.update_one(
        {"client_id": client_id},
        {"$push": {"items": item}, "$setOnInsert": {"client_id": client_id, "created_at": _now_iso()}},
        upsert=True,
    )
    await _send_invoice_email_if_possible(client_id, background_tasks)
    return item

@api_router.put("/clients/{client_id}/invoices/items/{item_id}")
async def update_invoice_item(client_id: str, item_id: str, payload: InvoiceItemCreate, background_tasks: BackgroundTasks):
    res = await db.invoices.update_one(
        {"client_id": client_id, "items.id": item_id},
        {"$set": {
            "items.$.description": payload.description,
            "items.$.amount": payload.amount,
            "items.$.status": payload.status,
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Item not found")
    await _send_invoice_email_if_possible(client_id, background_tasks)
    return {"ok": True}

@api_router.delete("/clients/{client_id}/invoices/items/{item_id}")
async def delete_invoice_item(client_id: str, item_id: str, background_tasks: BackgroundTasks):
    await db.invoices.update_one(
        {"client_id": client_id},
        {"$pull": {"items": {"id": item_id}}},
    )
    await _send_invoice_email_if_possible(client_id, background_tasks)
    return {"ok": True}


# --- Share link ---
@api_router.post("/clients/{client_id}/share")
async def create_share_link(client_id: str):
    c = await db.clients.find_one({"id": client_id}, {"_id": 0, "id": 1})
    if not c:
        raise HTTPException(404, "Client not found")
    existing = await db.share_tokens.find_one({"client_id": client_id}, {"_id": 0})
    if existing:
        token = existing["token"]
    else:
        token = secrets.token_urlsafe(16)
        await db.share_tokens.insert_one({"token": token, "client_id": client_id, "created_at": _now_iso()})
    return {"token": token, "url": f"{PUBLIC_BASE_URL}/api/share/{token}"}

@api_router.get("/share/{token}", response_class=HTMLResponse)
async def public_share(token: str):
    rec = await db.share_tokens.find_one({"token": token}, {"_id": 0})
    if not rec:
        return HTMLResponse("<h2 style='font-family:Georgia;margin:40px'>Link not found.</h2>", status_code=404)
    cid = rec["client_id"]
    c = await db.clients.find_one({"id": cid}, {"_id": 0})
    if not c:
        return HTMLResponse("<h2 style='font-family:Georgia;margin:40px'>Client not found.</h2>", status_code=404)
    pdfs_cursor = db.pdfs.find({"client_id": cid}, {"_id": 0, "data_base64": 0}).sort("uploaded_at", -1)
    pdfs = [d async for d in pdfs_cursor]
    inv = await db.invoices.find_one({"client_id": cid}, {"_id": 0}) or {"items": []}
    measurements_html = "".join(
        f"<tr><td style='padding:6px 12px 6px 0;color:#6B6761;text-transform:uppercase;font-size:11px;letter-spacing:.1em'>{k}</td><td style='padding:6px 0'>{v}</td></tr>"
        for k, v in (c.get("measurements") or {}).items()
    ) or "<tr><td style='color:#6B6761'>No measurements on file.</td></tr>"
    pdfs_html = "".join(
        f"<li style='padding:8px 0;border-bottom:1px solid #EAE5DA'>{p['name']} <span style='color:#6B6761;font-size:12px'>· {p['uploaded_at'][:10]}</span></li>"
        for p in pdfs
    ) or "<li style='color:#6B6761'>No design sheets yet.</li>"
    inv_items = inv.get("items", [])
    inv_rows = "".join(
        f"<tr><td style='padding:10px 0;border-bottom:1px solid #EAE5DA'>{it['description']}</td>"
        f"<td style='padding:10px 0;border-bottom:1px solid #EAE5DA;text-align:right'>₹{it['amount']:.2f}</td>"
        f"<td style='padding:10px 0;border-bottom:1px solid #EAE5DA;text-align:right;text-transform:uppercase;font-size:11px;letter-spacing:.1em;color:{'#5C6B5D' if it['status']=='cleared' else '#B38A58'}'>{it['status']}</td></tr>"
        for it in inv_items
    ) or "<tr><td style='color:#6B6761;padding:10px 0'>No invoice items.</td></tr>"
    return HTMLResponse(f"""<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{c['name']} — Atelier</title>
<style>body{{margin:0;background:#FDFBF7;color:#1A1918;font-family:Arial,sans-serif}}.wrap{{max-width:680px;margin:0 auto;padding:32px 24px}}h1{{font-family:Georgia,serif;font-weight:400;font-size:36px;margin:0 0 8px}}h2{{font-family:Georgia,serif;font-weight:400;font-size:20px;margin:32px 0 12px}}.kicker{{letter-spacing:.2em;text-transform:uppercase;color:#A3523B;font-size:12px}}</style>
</head><body><div class="wrap">
<p class="kicker">Atelier · Client Profile</p>
<h1>{c['name']}</h1>
<p style="color:#6B6761">{c.get('email','')} {('· ' + c['whatsapp']) if c.get('whatsapp') else ''}</p>
<h2>Measurements</h2><table>{measurements_html}</table>
<h2>Design Sheets</h2><ul style="list-style:none;padding:0;margin:0">{pdfs_html}</ul>
<h2>Invoice</h2><table style="width:100%;border-collapse:collapse">{inv_rows}</table>
<p style="color:#6B6761;font-size:12px;margin-top:48px">Shared via Atelier — read-only.</p>
</div></body></html>""")


# --- Events ---
@api_router.post("/schedule/parse")
async def schedule_parse(payload: ParseRequest):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "LLM key not configured")
    try:
        parsed = await parse_with_llm(payload.text, payload.default_tz)
    except Exception as e:
        logger.error(f"parse failed: {e}")
        raise HTTPException(400, f"Could not parse: {e}")
    # Match client by name
    client_id = None
    client_email = ""
    if parsed.get("client_name"):
        m = await db.clients.find_one(
            {"name": {"$regex": f"^{re.escape(parsed['client_name'])}", "$options": "i"}},
            {"_id": 0},
        )
        if m:
            client_id = m["id"]
            client_email = m.get("email", "")
            parsed["client_name"] = m["name"]
    parsed["client_id"] = client_id
    parsed["client_email"] = client_email
    return parsed

@api_router.post("/events", response_model=EventOut)
async def create_event(payload: EventCreate, background_tasks: BackgroundTasks):
    client_name = ""
    client_email = payload.client_email or ""
    if payload.client_id:
        c = await db.clients.find_one({"id": payload.client_id}, {"_id": 0})
        if c:
            client_name = c["name"]
            if not client_email:
                client_email = c.get("email", "")

    meet_link = _mock_meet_link()
    reminders = _reminders_for(payload.start_iso)
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
        "reminders": reminders,
        "created_at": _now_iso(),
    }
    await db.events.insert_one(doc)
    # Send invite email if we have client email
    if client_email and payload.mode != "personal":
        try:
            dt = date_parser.isoparse(payload.start_iso)
            when_human = dt.strftime("%A, %d %b %Y · %I:%M %p %Z")
        except Exception:
            when_human = payload.start_iso
        html = _meeting_html(doc["title"], when_human, meet_link, doc["notes"])
        background_tasks.add_task(_send_email_sync, client_email, f"{doc['title']} — Meeting invite", html)

    doc.pop("_id", None)
    return EventOut(**doc)

@api_router.get("/events", response_model=List[EventOut])
async def list_events(from_iso: Optional[str] = None, to_iso: Optional[str] = None):
    q = {}
    if from_iso and to_iso:
        q = {"start_iso": {"$gte": from_iso, "$lte": to_iso}}
    cursor = db.events.find(q, {"_id": 0}).sort("start_iso", 1)
    return [EventOut(**d) async for d in cursor]

@api_router.delete("/events/{event_id}")
async def delete_event(event_id: str):
    await db.events.delete_one({"id": event_id})
    return {"ok": True}


# --- Voice transcription ---
@api_router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "LLM key not configured")
    suffix_map = {
        "audio/m4a": ".m4a", "audio/x-m4a": ".m4a", "audio/mp4": ".m4a",
        "audio/mpeg": ".mp3", "audio/mp3": ".mp3",
        "audio/wav": ".wav", "audio/x-wav": ".wav",
        "audio/webm": ".webm", "audio/ogg": ".webm",
    }
    # Prefer original filename extension if reasonable
    name = audio.filename or ""
    ext = ""
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1].lower()
    if ext not in {".m4a", ".mp3", ".wav", ".webm", ".mp4", ".mpeg", ".mpga"}:
        ext = suffix_map.get(audio.content_type or "", ".m4a")

    data = await audio.read()
    if not data:
        raise HTTPException(400, "Empty audio")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
        with open(tmp_path, "rb") as fh:
            res = await stt.transcribe(file=fh, model="whisper-1", response_format="json")
        text = ""
        if hasattr(res, "text"):
            text = res.text
        elif isinstance(res, dict):
            text = res.get("text", "")
        else:
            text = str(res)
        return {"text": text.strip()}
    except Exception as e:
        logger.error(f"transcribe failed: {e}")
        raise HTTPException(500, f"Transcription failed: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# --- Seed ---
@api_router.post("/_seed")
async def seed_demo():
    if await db.clients.count_documents({}) > 0:
        return {"ok": True, "skipped": True}
    demo = [
        {"id": str(uuid.uuid4()), "name": "Anaïs Mehta", "whatsapp": "+91 98765 12345", "email": "anais@example.com",
         "measurements": {"Bust": "34\"", "Waist": "26\"", "Hip": "36\"", "Shoulder": "14\""},
         "notes": "Prefers structured silhouettes.", "created_at": _now_iso(), "avatar_url": None},
        {"id": str(uuid.uuid4()), "name": "Riya Kapoor", "whatsapp": "+91 99887 66554", "email": "riya@example.com",
         "measurements": {"Bust": "32\"", "Waist": "24\"", "Hip": "34\""},
         "notes": "Loves silk crepe and earthy tones.", "created_at": _now_iso(), "avatar_url": None},
        {"id": str(uuid.uuid4()), "name": "Leah Sinha", "whatsapp": "", "email": "",
         "measurements": {}, "notes": "", "created_at": _now_iso(), "avatar_url": None},
    ]
    await db.clients.insert_many(demo)
    return {"ok": True, "count": len(demo)}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client_mongo.close()
