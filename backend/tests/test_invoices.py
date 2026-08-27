"""tests/test_invoices.py — Invoice item CRUD tests."""
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
def invoice_client(s):
    c = s.post(f"{API}/clients", json={"name": "TEST_Invoice Client", "email": "inv@test-atelier.com"}, timeout=20).json()
    yield c
    s.delete(f"{API}/clients/{c['id']}", timeout=20)


def test_add_invoice_item(s, invoice_client):
    cid = invoice_client["id"]
    r = s.post(
        f"{API}/clients/{cid}/invoices/items",
        json={"description": "TEST_Sketch v1", "amount": 2500, "status": "pending"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["amount"] == 2500
    assert item["status"] == "pending"
    assert "id" in item
    assert "created_at" in item
    return item["id"]


def test_invoice_item_persists(s, invoice_client):
    cid = invoice_client["id"]
    # Add item
    add = s.post(
        f"{API}/clients/{cid}/invoices/items",
        json={"description": "PERSIST_TEST", "amount": 1000},
        timeout=20,
    )
    assert add.status_code == 200
    item_id = add.json()["id"]

    # Verify via GET client
    g = s.get(f"{API}/clients/{cid}", timeout=20).json()
    ids = [i["id"] for i in g["invoice"]["items"]]
    assert item_id in ids

    # Cleanup
    s.delete(f"{API}/clients/{cid}/invoices/items/{item_id}", timeout=20)


def test_update_invoice_item(s, invoice_client):
    cid = invoice_client["id"]
    add = s.post(
        f"{API}/clients/{cid}/invoices/items",
        json={"description": "UPDATE_TEST", "amount": 500},
        timeout=20,
    ).json()
    item_id = add["id"]

    up = s.put(
        f"{API}/clients/{cid}/invoices/items/{item_id}",
        json={"description": "UPDATE_TEST v2", "amount": 750, "status": "cleared"},
        timeout=20,
    )
    assert up.status_code == 200

    g = s.get(f"{API}/clients/{cid}", timeout=20).json()
    matched = [i for i in g["invoice"]["items"] if i["id"] == item_id]
    assert matched, "Updated item not found"
    assert matched[0]["status"] == "cleared"
    assert matched[0]["amount"] == 750

    # Cleanup
    s.delete(f"{API}/clients/{cid}/invoices/items/{item_id}", timeout=20)


def test_delete_invoice_item(s, invoice_client):
    cid = invoice_client["id"]
    add = s.post(
        f"{API}/clients/{cid}/invoices/items",
        json={"description": "DELETE_TEST", "amount": 100},
        timeout=20,
    ).json()
    item_id = add["id"]

    d = s.delete(f"{API}/clients/{cid}/invoices/items/{item_id}", timeout=20)
    assert d.status_code == 200

    g = s.get(f"{API}/clients/{cid}", timeout=20).json()
    assert not any(i["id"] == item_id for i in g["invoice"]["items"])


def test_update_nonexistent_item_404(s, invoice_client):
    cid = invoice_client["id"]
    r = s.put(
        f"{API}/clients/{cid}/invoices/items/does-not-exist",
        json={"description": "x", "amount": 1},
        timeout=20,
    )
    assert r.status_code == 404
