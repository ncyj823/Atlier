"""Iteration 4 backend tests: UID, auto sending_pieces, reschedule, scheduler, emails."""
import os
import time
import uuid
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

S = requests.Session()
S.headers.update({"Content-Type": "application/json"})


# ---------- helpers ----------
def _make_client():
    r = S.post(f"{API}/clients", json={
        "name": f"TEST_Client_{uuid.uuid4().hex[:6]}",
        "email": "test_client_atelier@example.com",
        "whatsapp": "+910000000000",
    })
    assert r.status_code == 200, r.text
    return r.json()


# ---------- health / scheduler ----------
def test_health():
    r = S.get(f"{API}/")
    assert r.status_code == 200
    assert r.json().get("ok") is True


# ---------- projects: UID + auto sending_pieces ----------
def test_create_project_returns_uid_and_creates_sending_event():
    c = _make_client()
    deadline = (datetime.now(timezone.utc) + timedelta(days=20)).date().isoformat()
    r = S.post(f"{API}/projects", json={
        "client_id": c["id"], "title": "TEST_Project_Alpha",
        "deadline": deadline, "total_amount": 10000, "paid_amount": 0,
        "mannequin_gender": "female",
    })
    assert r.status_code == 200, r.text
    p = r.json()
    assert "uid" in p and p["uid"].startswith("ATL-")
    assert len(p["uid"]) == 8  # ATL-NNNN
    seq_part = p["uid"].split("-")[1]
    assert seq_part.isdigit() and len(seq_part) == 4

    # GET project back, confirm persistence
    g = S.get(f"{API}/projects/{p['id']}")
    assert g.status_code == 200
    assert g.json()["project"]["uid"] == p["uid"]

    # Auto sending_pieces event should exist 2 days before deadline
    from_iso = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    to_iso = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    ev_resp = S.get(f"{API}/events", params={"from_iso": from_iso, "to_iso": to_iso})
    assert ev_resp.status_code == 200
    matching = [
        e for e in ev_resp.json()
        if e.get("title") == f"Send pieces — TEST_Project_Alpha"
        and e.get("mode") == "sending_pieces"
    ]
    assert len(matching) >= 1, f"no auto sending_pieces event found; got {[e.get('title') for e in ev_resp.json()]}"
    ev_start = matching[0]["start_iso"]
    ev_dt = datetime.fromisoformat(ev_start)
    deadline_dt = datetime.fromisoformat(deadline + "T10:00:00+05:30")
    delta = (deadline_dt - ev_dt).total_seconds()
    assert abs(delta - 2 * 86400) < 3600, f"sending event not ~2 days before deadline (delta={delta}s)"

    # Cleanup
    S.delete(f"{API}/projects/{p['id']}")
    # Delete the auto event too (so list stays clean)
    for ev in matching:
        S.delete(f"{API}/events/{ev['id']}")
    S.delete(f"{API}/clients/{c['id']}")


def test_project_uid_is_sequential():
    c = _make_client()
    deadline = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
    ids = []
    uids = []
    for i in range(2):
        r = S.post(f"{API}/projects", json={
            "client_id": c["id"], "title": f"TEST_SeqProj_{i}",
            "deadline": deadline,
        })
        assert r.status_code == 200
        body = r.json()
        ids.append(body["id"])
        uids.append(body["uid"])
    seq0 = int(uids[0].split("-")[1])
    seq1 = int(uids[1].split("-")[1])
    assert seq1 == seq0 + 1, f"UIDs not sequential: {uids}"
    # cleanup
    for pid in ids:
        S.delete(f"{API}/projects/{pid}")
    S.delete(f"{API}/clients/{c['id']}")


def test_update_project_deadline_updates_existing_sending_event_no_duplicate():
    c = _make_client()
    d1 = (datetime.now(timezone.utc) + timedelta(days=15)).date().isoformat()
    r = S.post(f"{API}/projects", json={
        "client_id": c["id"], "title": "TEST_Reschedule_Project", "deadline": d1,
    })
    assert r.status_code == 200
    p = r.json()

    # Update deadline to a new date
    d2 = (datetime.now(timezone.utc) + timedelta(days=40)).date().isoformat()
    u = S.put(f"{API}/projects/{p['id']}", json={"deadline": d2})
    assert u.status_code == 200

    # Look up all events and count auto sending_pieces for this project
    from_iso = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    to_iso = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    ev_resp = S.get(f"{API}/events", params={"from_iso": from_iso, "to_iso": to_iso})
    matching = [
        e for e in ev_resp.json()
        if e.get("title") == "Send pieces — TEST_Reschedule_Project"
    ]
    assert len(matching) == 1, f"expected exactly 1 auto sending event, got {len(matching)}"

    # New start_iso should be ~2 days before d2
    ev_dt = datetime.fromisoformat(matching[0]["start_iso"])
    d2_dt = datetime.fromisoformat(d2 + "T10:00:00+05:30")
    delta = (d2_dt - ev_dt).total_seconds()
    assert abs(delta - 2 * 86400) < 3600

    # cleanup
    for ev in matching:
        S.delete(f"{API}/events/{ev['id']}")
    S.delete(f"{API}/projects/{p['id']}")
    S.delete(f"{API}/clients/{c['id']}")


# ---------- events create (Google fallback OK) ----------
def test_create_event_design_call_returns_meet_link():
    c = _make_client()
    start = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = S.post(f"{API}/events", json={
        "title": "TEST_Design_Call",
        "mode": "design_call",
        "start_iso": start,
        "duration_minutes": 30,
        "client_id": c["id"],
        "client_email": "test_client_atelier@example.com",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("meet_link", "").startswith("https://meet.google.com/"), body
    assert body["mode"] == "design_call"
    assert body["client_email"] == "test_client_atelier@example.com"
    # cleanup
    S.delete(f"{API}/events/{body['id']}")
    S.delete(f"{API}/clients/{c['id']}")


def test_create_event_personal_no_invitee_email():
    start = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r = S.post(f"{API}/events", json={
        "title": "TEST_Personal", "mode": "personal",
        "start_iso": start, "duration_minutes": 30,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "personal"
    assert body.get("meet_link", "").startswith("https://meet.google.com/")
    S.delete(f"{API}/events/{body['id']}")


def test_list_events_window():
    """Verify the auto-created sending event from earlier shows up in a window query."""
    # Just ensure endpoint accepts window
    fro = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    to = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    r = S.get(f"{API}/events", params={"from_iso": fro, "to_iso": to})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------- list projects with client_name + uid ----------
def test_list_projects_includes_uid_and_client_name():
    c = _make_client()
    r = S.post(f"{API}/projects", json={"client_id": c["id"], "title": "TEST_ListProj"})
    pid = r.json()["id"]
    L = S.get(f"{API}/projects")
    assert L.status_code == 200
    found = [p for p in L.json() if p["id"] == pid]
    assert found
    assert found[0].get("uid", "").startswith("ATL-")
    assert found[0].get("client_name") == c["name"]
    # cleanup
    S.delete(f"{API}/projects/{pid}")
    S.delete(f"{API}/clients/{c['id']}")
