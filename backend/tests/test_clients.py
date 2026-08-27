"""tests/test_clients.py — Client CRUD tests."""
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
def created_client(s):
    payload = {
        "name": "TEST_Client Alpha",
        "email": "alpha@test-atelier.com",
        "whatsapp": "+91 90000 11111",
        "measurements": {"Bust": '33"', "Waist": '25"'},
        "notes": "TEST fixture client",
    }
    r = s.post(f"{API}/clients", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    yield data
    # Teardown
    s.delete(f"{API}/clients/{data['id']}", timeout=20)


def test_seed_idempotent(s):
    r1 = s.post(f"{API}/_seed", timeout=20)
    assert r1.status_code == 200
    assert r1.json().get("ok") is True
    r2 = s.post(f"{API}/_seed", timeout=20)
    assert r2.status_code == 200
    assert r2.json().get("ok") is True
    assert r2.json().get("skipped") is True or r2.json().get("count")


def test_list_clients_no_mongo_id(s, created_client):
    r = s.get(f"{API}/clients", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    for c in data:
        assert "_id" not in c
        assert "id" in c
        assert "name" in c


def test_create_client_returns_correct_shape(created_client):
    assert "id" in created_client
    assert created_client["name"] == "TEST_Client Alpha"
    assert created_client["email"] == "alpha@test-atelier.com"
    assert "_id" not in created_client


def test_get_client_bundle(s, created_client):
    r = s.get(f"{API}/clients/{created_client['id']}", timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"client", "pdfs", "invoice"}
    assert body["client"]["id"] == created_client["id"]
    assert isinstance(body["pdfs"], list)
    assert "items" in body["invoice"]


def test_update_client(s, created_client):
    r = s.put(
        f"{API}/clients/{created_client['id']}",
        json={"notes": "Updated note"},
        timeout=20,
    )
    assert r.status_code == 200
    assert r.json()["notes"] == "Updated note"
    # Other fields untouched
    assert r.json()["name"] == "TEST_Client Alpha"


def test_update_client_invalid_email(s, created_client):
    r = s.put(
        f"{API}/clients/{created_client['id']}",
        json={"email": "not-an-email"},
        timeout=20,
    )
    assert r.status_code == 422


def test_create_client_invalid_email(s):
    r = s.post(
        f"{API}/clients",
        json={"name": "Bad Email", "email": "bad@"},
        timeout=20,
    )
    assert r.status_code == 422


def test_get_nonexistent_client_404(s):
    r = s.get(f"{API}/clients/does-not-exist-abc123", timeout=20)
    assert r.status_code == 404


def test_delete_client_removes_all_data(s):
    # Create a client with related data
    c = s.post(f"{API}/clients", json={"name": "TO_DELETE"}, timeout=20).json()
    cid = c["id"]
    # Add an invoice item
    s.post(f"{API}/clients/{cid}/invoices/items",
           json={"description": "test", "amount": 100}, timeout=20)
    # Create a share link
    s.post(f"{API}/clients/{cid}/share", timeout=20)
    # Delete
    r = s.delete(f"{API}/clients/{cid}", timeout=20)
    assert r.status_code == 200
    assert r.json().get("ok") is True
    # Verify gone
    g = s.get(f"{API}/clients/{cid}", timeout=20)
    assert g.status_code == 404
