"""tests/test_projects.py — Project CRUD, canvas, and client projects tests."""
import base64
import pytest
import requests
from tests.conftest import BASE_URL, API_KEY

API = f"{BASE_URL}/api"
HEADERS = {"Content-Type": "application/json", "X-API-Key": API_KEY}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update(HEADERS)
    return sess


@pytest.fixture(scope="module")
def project_client(s):
    c = s.post(
        f"{API}/clients",
        json={"name": "TEST_Project Client"},
        timeout=20,
    ).json()
    yield c
    s.delete(f"{API}/clients/{c['id']}", timeout=20)


@pytest.fixture(scope="module")
def created_project(s, project_client):
    payload = {
        "client_id": project_client["id"],
        "title": "TEST_Summer Collection",
        "delivery_location": "Mumbai",
        "deadline": "2026-12-15",
        "description": "TEST project",
        "total_amount": 80000,
        "paid_amount": 20000,
        "mannequin_gender": "male",
    }
    r = s.post(f"{API}/projects", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    yield data
    s.delete(f"{API}/projects/{data['id']}", timeout=20)


def test_create_project_shape(created_project, project_client):
    assert "id" in created_project
    assert "uid" in created_project
    assert created_project["uid"].startswith("ATL-")
    assert created_project["client_id"] == project_client["id"]
    assert created_project["title"] == "TEST_Summer Collection"
    assert created_project["status"] == "ongoing"
    assert created_project["client_name"]
    assert "_id" not in created_project


def test_list_projects_has_client_name(s, created_project):
    r = s.get(f"{API}/projects", timeout=20)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    for p in items:
        assert "client_name" in p
        assert "deadline" in p
    # Sorted by deadline asc (no deadline last)
    deadlines = [p.get("deadline") or "9999-12-31" for p in items]
    assert deadlines == sorted(deadlines)


def test_get_project_bundle(s, created_project):
    r = s.get(f"{API}/projects/{created_project['id']}", timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert set(["project", "client", "pdfs", "canvas"]).issubset(d.keys())
    assert d["project"]["id"] == created_project["id"]
    assert d["client"] is not None
    assert isinstance(d["pdfs"], list)
    assert d["canvas"]["gender"] in ("male", "female")


def test_canvas_auto_created_with_correct_gender(s, created_project):
    r = s.get(f"{API}/projects/{created_project['id']}/canvas", timeout=20)
    assert r.status_code == 200
    c = r.json()
    assert c["project_id"] == created_project["id"]
    assert c["gender"] == "male"
    assert c["strokes"] == []


def test_canvas_save_and_load(s, created_project):
    strokes = [
        {"d": "M10 10 L50 60", "color": "#A3523B", "width": 3},
        {"d": "M20 20 L80 80", "color": "#000000", "width": 2},
    ]
    r = s.put(
        f"{API}/projects/{created_project['id']}/canvas",
        json={"gender": "female", "strokes": strokes},
        timeout=20,
    )
    assert r.status_code == 200

    g = s.get(f"{API}/projects/{created_project['id']}/canvas", timeout=20).json()
    assert g["gender"] == "female"
    assert len(g["strokes"]) == 2
    assert g["strokes"][0]["color"] == "#A3523B"


def test_update_project_status(s, created_project):
    r = s.put(
        f"{API}/projects/{created_project['id']}",
        json={"status": "completed"},
        timeout=20,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
    # Flip back
    s.put(f"{API}/projects/{created_project['id']}", json={"status": "ongoing"}, timeout=20)


def test_project_pdf_upload(s, created_project):
    data_b64 = base64.b64encode(b"%PDF-1.4 test content").decode()
    r = s.post(
        f"{API}/projects/{created_project['id']}/pdfs",
        json={"name": "TEST_sheet.pdf", "data_base64": data_b64},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    pdf = r.json()
    assert pdf["name"] == "TEST_sheet.pdf"
    assert pdf["size_bytes"] > 0

    # Verify in bundle
    bundle = s.get(f"{API}/projects/{created_project['id']}", timeout=20).json()
    assert any(p["id"] == pdf["id"] for p in bundle["pdfs"])

    # Cleanup
    s.delete(f"{API}/projects/{created_project['id']}/pdfs/{pdf['id']}", timeout=20)


def test_client_projects_endpoint(s, created_project, project_client):
    r = s.get(f"{API}/clients/{project_client['id']}/projects", timeout=20)
    assert r.status_code == 200
    items = r.json()
    ids = [p["id"] for p in items]
    assert created_project["id"] in ids


def test_get_unknown_project_404(s):
    r = s.get(f"{API}/projects/does-not-exist", timeout=20)
    assert r.status_code == 404


def test_create_project_unknown_client_404(s):
    r = s.post(
        f"{API}/projects",
        json={"client_id": "no-such-client", "title": "TEST"},
        timeout=20,
    )
    assert r.status_code == 404
