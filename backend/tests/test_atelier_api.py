"""Backend API tests for Atelier MVP."""
import os
import pytest
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://style-manager-29.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# --- Root ---
def test_root_ok(s):
    r = s.get(f"{API}/")
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert j.get("app") == "Atelier"


# --- Seed (idempotent) ---
def test_seed_idempotent(s):
    r1 = s.post(f"{API}/_seed")
    assert r1.status_code == 200
    assert r1.json().get("ok") is True
    r2 = s.post(f"{API}/_seed")
    assert r2.status_code == 200
    assert r2.json().get("ok") is True
    # second call must skip
    assert r2.json().get("skipped") is True or r2.json().get("count")


# --- Clients ---
def test_list_clients_no_underscore_id(s):
    r = s.get(f"{API}/clients")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    for c in data:
        assert "_id" not in c
        assert "id" in c and "name" in c


def test_create_and_get_client(s):
    payload = {"name": "TEST_Pytest Client", "email": "test_pytest@example.com", "whatsapp": "+91 90000 00000",
               "measurements": {"Bust": "33\""}, "notes": "TEST"}
    r = s.post(f"{API}/clients", json=payload)
    assert r.status_code == 200
    created = r.json()
    cid = created["id"]
    assert created["name"] == payload["name"]
    assert "_id" not in created

    g = s.get(f"{API}/clients/{cid}")
    assert g.status_code == 200
    body = g.json()
    assert set(body.keys()) >= {"client", "pdfs", "invoice"}
    assert body["client"]["id"] == cid
    assert body["client"]["name"] == payload["name"]
    assert isinstance(body["pdfs"], list)
    return cid


# --- NL parse ---
def test_schedule_parse_design_call_ist(s):
    text = "Schedule a design call for Anaïs at 6pm IST on coming Wednesday"
    r = s.post(f"{API}/schedule/parse", json={"text": text, "default_tz": "Asia/Kolkata"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("mode") == "design_call"
    # tz offset should be IST +05:30
    start = j.get("start_iso", "")
    assert "+05:30" in start
    # future date
    parsed_dt = datetime.fromisoformat(start)
    assert parsed_dt > datetime.now(parsed_dt.tzinfo)
    # client linkage may match Anaïs Mehta seeded client
    assert j.get("client_name") is None or "Ana" in j.get("client_name", "")


# --- Events ---
def test_create_event_returns_meet_and_reminders(s):
    start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0).isoformat()
    payload = {"title": "TEST_Event", "mode": "design_call", "start_iso": start, "duration_minutes": 30,
               "notes": "TEST"}
    r = s.post(f"{API}/events", json=payload)
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["meet_link"].startswith("https://meet.google.com/")
    assert isinstance(e["reminders"], list) and len(e["reminders"]) == 3
    return e["id"]


def test_list_events_range(s):
    start = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    r = s.get(f"{API}/events", params={"from_iso": start, "to_iso": end})
    assert r.status_code == 200
    arr = r.json()
    assert isinstance(arr, list)
    assert len(arr) >= 1


# --- Invoice CRUD ---
def test_invoice_item_crud_and_share(s):
    # create dedicated client
    c = s.post(f"{API}/clients", json={"name": "TEST_Invoice Client", "email": "ti@example.com"}).json()
    cid = c["id"]

    # add
    add = s.post(f"{API}/clients/{cid}/invoices/items",
                 json={"description": "TEST_Sketch", "amount": 2500, "status": "pending"})
    assert add.status_code == 200
    item = add.json()
    item_id = item["id"]
    assert item["amount"] == 2500

    # verify persistence via GET client
    g = s.get(f"{API}/clients/{cid}").json()
    assert any(i["id"] == item_id for i in g["invoice"]["items"])

    # update
    up = s.put(f"{API}/clients/{cid}/invoices/items/{item_id}",
               json={"description": "TEST_Sketch v2", "amount": 3000, "status": "cleared"})
    assert up.status_code == 200
    g2 = s.get(f"{API}/clients/{cid}").json()
    matched = [i for i in g2["invoice"]["items"] if i["id"] == item_id][0]
    assert matched["status"] == "cleared" and matched["amount"] == 3000

    # delete
    d = s.delete(f"{API}/clients/{cid}/invoices/items/{item_id}")
    assert d.status_code == 200
    g3 = s.get(f"{API}/clients/{cid}").json()
    assert not any(i["id"] == item_id for i in g3["invoice"]["items"])

    # share link
    sh = s.post(f"{API}/clients/{cid}/share")
    assert sh.status_code == 200
    tok = sh.json()["token"]
    assert sh.json()["url"].endswith(tok)

    pub = requests.get(f"{API}/share/{tok}")
    assert pub.status_code == 200
    assert "TEST_Invoice Client" in pub.text
    assert "text/html" in pub.headers.get("content-type", "")
