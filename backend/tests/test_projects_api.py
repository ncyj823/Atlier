"""Backend tests for the Projects redesign (iteration 3).

Covers:
- GET /api/projects sort + client_name attached
- POST /api/projects creates project + canvas
- GET /api/projects/{id} returns project + client + pdfs + canvas
- PUT /api/projects/{id} status flip
- POST /api/projects/{id}/pdfs upload
- PUT/GET /api/projects/{id}/canvas
- GET /api/clients/{id}/projects
"""
import os
import base64
import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    os.environ.get("ATELIER_TEST_URL", "http://localhost:8000"),
).rstrip("/")
API_KEY = os.environ.get("ATELIER_TEST_API_KEY", os.environ.get("API_KEY", ""))


@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-API-Key": API_KEY})
    return s


@pytest.fixture(scope="session")
def seeded_client_id(api_client):
    # Ensure at least one client exists (idempotent)
    api_client.post(f"{BASE_URL}/api/_seed", timeout=20)
    r = api_client.get(f"{BASE_URL}/api/clients", timeout=20)
    assert r.status_code == 200, r.text
    clients = r.json()
    assert clients, "expected seeded clients"
    return clients[0]["id"]


@pytest.fixture(scope="session")
def created_project(api_client, seeded_client_id):
    payload = {
        "client_id": seeded_client_id,
        "title": "TEST_Project Iteration3",
        "delivery_location": "Mumbai",
        "deadline": "2026-08-15",
        "description": "TEST project",
        "total_amount": 50000,
        "paid_amount": 10000,
        "mannequin_gender": "male",
    }
    r = api_client.post(f"{BASE_URL}/api/projects", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["title"] == payload["title"]
    assert data["client_id"] == seeded_client_id
    assert data["status"] == "ongoing"
    assert data["client_name"]
    yield data
    # teardown
    api_client.delete(f"{BASE_URL}/api/projects/{data['id']}", timeout=20)


# ---------- listProjects ----------
class TestProjectList:
    def test_list_has_client_name_and_sorted(self, api_client, created_project):
        r = api_client.get(f"{BASE_URL}/api/projects", timeout=20)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list) and len(items) >= 1
        # Every item has a client_name field (may be empty string if orphaned)
        for p in items:
            assert "client_name" in p
            assert "deadline" in p
        # Sort: items with deadline ascending, None last
        deadlines = [p.get("deadline") or "9999-12-31" for p in items]
        assert deadlines == sorted(deadlines), f"projects not sorted by deadline asc: {deadlines}"


# ---------- create auto-creates canvas ----------
class TestCreateCanvasLinked:
    def test_canvas_autocreated_with_gender(self, api_client, created_project):
        r = api_client.get(f"{BASE_URL}/api/projects/{created_project['id']}/canvas", timeout=20)
        assert r.status_code == 200
        c = r.json()
        assert c["project_id"] == created_project["id"]
        assert c["gender"] == "male", f"expected male, got {c.get('gender')}"
        assert c["strokes"] == []


# ---------- get project bundle ----------
class TestGetProjectBundle:
    def test_bundle_has_all_keys(self, api_client, created_project):
        r = api_client.get(f"{BASE_URL}/api/projects/{created_project['id']}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert set(["project", "client", "pdfs", "canvas"]).issubset(d.keys())
        assert d["project"]["id"] == created_project["id"]
        assert d["client"] and d["client"]["id"] == created_project["client_id"]
        assert isinstance(d["pdfs"], list)
        assert d["canvas"]["gender"] in ("male", "female")


# ---------- status update ----------
class TestStatusUpdate:
    def test_flip_to_completed(self, api_client, created_project):
        r = api_client.put(
            f"{BASE_URL}/api/projects/{created_project['id']}",
            json={"status": "completed"},
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "completed"
        # verify via GET
        g = api_client.get(f"{BASE_URL}/api/projects/{created_project['id']}", timeout=20).json()
        assert g["project"]["status"] == "completed"
        # flip back
        api_client.put(
            f"{BASE_URL}/api/projects/{created_project['id']}",
            json={"status": "ongoing"},
            timeout=20,
        )


# ---------- pdf upload ----------
class TestProjectPdf:
    def test_upload_pdf(self, api_client, created_project):
        data_b64 = base64.b64encode(b"%PDF-1.4 test pdf bytes").decode()
        r = api_client.post(
            f"{BASE_URL}/api/projects/{created_project['id']}/pdfs",
            json={"name": "TEST_sheet.pdf", "data_base64": data_b64},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        pdf = r.json()
        assert pdf["name"] == "TEST_sheet.pdf"
        assert pdf["size_bytes"] > 0
        # verify via project bundle
        g = api_client.get(f"{BASE_URL}/api/projects/{created_project['id']}", timeout=20).json()
        assert any(p["id"] == pdf["id"] for p in g["pdfs"])
        # cleanup
        api_client.delete(
            f"{BASE_URL}/api/projects/{created_project['id']}/pdfs/{pdf['id']}", timeout=20
        )


# ---------- canvas save/load ----------
class TestCanvasSaveLoad:
    def test_save_and_get_strokes(self, api_client, created_project):
        strokes = [
            {"d": "M10 10 L50 60", "color": "#A3523B", "width": 3},
            {"d": "M20 20 L80 80", "color": "#000000", "width": 2},
        ]
        r = api_client.put(
            f"{BASE_URL}/api/projects/{created_project['id']}/canvas",
            json={"gender": "female", "strokes": strokes},
            timeout=20,
        )
        assert r.status_code == 200
        # GET back
        g = api_client.get(
            f"{BASE_URL}/api/projects/{created_project['id']}/canvas", timeout=20
        ).json()
        assert g["gender"] == "female"
        assert len(g["strokes"]) == 2
        assert g["strokes"][0]["d"] == "M10 10 L50 60"
        assert g["strokes"][0]["color"] == "#A3523B"
        assert g["strokes"][0]["width"] == 3


# ---------- client projects ----------
class TestClientProjects:
    def test_client_projects_includes_created(self, api_client, created_project):
        r = api_client.get(
            f"{BASE_URL}/api/clients/{created_project['client_id']}/projects", timeout=20
        )
        assert r.status_code == 200
        items = r.json()
        ids = [p["id"] for p in items]
        assert created_project["id"] in ids
        # sort respected
        deadlines = [p.get("deadline") or "9999-12-31" for p in items]
        assert deadlines == sorted(deadlines)


# ---------- 404 paths ----------
class TestNotFound:
    def test_get_unknown_project_404(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/projects/does-not-exist", timeout=20)
        assert r.status_code == 404

    def test_create_with_unknown_client_404(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/projects",
            json={"client_id": "no-such-client", "title": "TEST"},
            timeout=20,
        )
        assert r.status_code == 404
