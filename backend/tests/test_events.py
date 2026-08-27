"""tests/test_events.py — Event CRUD, share link, and NLP parse tests."""
import pytest
import requests
from datetime import datetime, timedelta, timezone
from tests.conftest import BASE_URL, API_KEY

API = f"{BASE_URL}/api"
HEADERS = {"Content-Type": "application/json", "X-API-Key": API_KEY}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update(HEADERS)
    return sess


@pytest.fixture(scope="module")
def created_event(s):
    start = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0).isoformat()
    r = s.post(
        f"{API}/events",
        json={
            "title": "TEST_Design Call",
            "mode": "design_call",
            "start_iso": start,
            "duration_minutes": 45,
            "notes": "TEST event",
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    yield data
    s.delete(f"{API}/events/{data['id']}", timeout=20)


def test_create_event_returns_meet_link(created_event):
    assert created_event["meet_link"].startswith("https://meet.google.com/")


def test_create_event_returns_three_reminders(created_event):
    reminders = created_event.get("reminders", [])
    assert isinstance(reminders, list)
    assert len(reminders) == 3


def test_create_event_fields(created_event):
    assert created_event["title"] == "TEST_Design Call"
    assert created_event["mode"] == "design_call"
    assert "id" in created_event
    assert "created_at" in created_event
    assert "_id" not in created_event


def test_list_events(s):
    r = s.get(f"{API}/events", timeout=20)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_events_date_range(s, created_event):
    start = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    r = s.get(f"{API}/events", params={"from_iso": start, "to_iso": end}, timeout=20)
    assert r.status_code == 200
    arr = r.json()
    assert isinstance(arr, list)
    ids = [e["id"] for e in arr]
    assert created_event["id"] in ids


def test_reschedule_event(s, created_event):
    new_start = (datetime.now(timezone.utc) + timedelta(days=5)).replace(microsecond=0).isoformat()
    r = s.put(
        f"{API}/events/{created_event['id']}",
        json={"start_iso": new_start},
        timeout=20,
    )
    assert r.status_code == 200
    updated = r.json()
    assert updated["start_iso"] == new_start
    assert len(updated["reminders"]) == 3


def test_reschedule_nonexistent_event_404(s):
    r = s.put(
        f"{API}/events/does-not-exist-xyz",
        json={"start_iso": "2026-01-01T10:00:00+05:30"},
        timeout=20,
    )
    assert r.status_code == 404


def test_delete_event(s):
    start = (datetime.now(timezone.utc) + timedelta(days=10)).replace(microsecond=0).isoformat()
    ev = s.post(
        f"{API}/events",
        json={"title": "TO_DELETE", "mode": "personal", "start_iso": start},
        timeout=20,
    ).json()
    r = s.delete(f"{API}/events/{ev['id']}", timeout=20)
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_share_link_create_and_public(s):
    # Create a client
    c = s.post(f"{API}/clients", json={"name": "TEST_Share Client"}, timeout=20).json()
    cid = c["id"]
    try:
        sh = s.post(f"{API}/clients/{cid}/share", timeout=20)
        assert sh.status_code == 200
        tok = sh.json()["token"]
        assert sh.json()["url"].endswith(tok)

        # Public page (no auth)
        pub = requests.get(f"{API}/share/{tok}", timeout=20)
        assert pub.status_code == 200
        assert "TEST_Share Client" in pub.text
        assert "text/html" in pub.headers.get("content-type", "")

        # Idempotent — second call returns same token
        sh2 = s.post(f"{API}/clients/{cid}/share", timeout=20)
        assert sh2.json()["token"] == tok
    finally:
        s.delete(f"{API}/clients/{cid}", timeout=20)
