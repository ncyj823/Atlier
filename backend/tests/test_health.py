"""tests/test_health.py — Health endpoint tests."""
import pytest
import requests
from tests.conftest import BASE_URL


def test_health_ok():
    r = requests.get(f"{BASE_URL}/health", timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert j.get("status") == "ok"


def test_health_db_ok():
    r = requests.get(f"{BASE_URL}/health/db", timeout=15)
    assert r.status_code in (200, 503), r.text
    j = r.json()
    assert "status" in j
    if r.status_code == 200:
        assert j["status"] == "ok"
        assert "latency_ms" in j
        assert isinstance(j["latency_ms"], (int, float))
    else:
        assert j["status"] == "error"


def test_health_no_auth_required():
    """Health endpoints must work without an API key."""
    r = requests.get(f"{BASE_URL}/health", timeout=10)
    assert r.status_code == 200


def test_root_ok():
    r = requests.get(f"{BASE_URL}/api/", timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert j.get("app") == "Atelier"
