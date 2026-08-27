"""tests/test_auth.py — Authentication behaviour tests."""
import requests
import pytest
from tests.conftest import BASE_URL, API_KEY


API = f"{BASE_URL}/api"


def test_missing_api_key_returns_401():
    """A request with no X-API-Key header must return 401."""
    r = requests.get(f"{API}/clients", timeout=10)
    assert r.status_code == 401
    j = r.json()
    assert "detail" in j


def test_wrong_api_key_returns_401():
    """A request with an incorrect X-API-Key must return 401."""
    r = requests.get(
        f"{API}/clients",
        headers={"X-API-Key": "definitely_wrong_key_12345"},
        timeout=10,
    )
    assert r.status_code == 401
    j = r.json()
    assert "detail" in j


def test_correct_api_key_returns_200():
    """A request with the correct X-API-Key must be allowed through."""
    if not API_KEY:
        pytest.skip("API_KEY not set in environment")
    r = requests.get(
        f"{API}/clients",
        headers={"X-API-Key": API_KEY},
        timeout=10,
    )
    assert r.status_code == 200


def test_public_share_requires_no_key():
    """The public share page should NOT require an API key."""
    # A non-existent token — should return 404 HTML, not 401.
    r = requests.get(f"{API}/share/nonexistent_token_xyz", timeout=10)
    assert r.status_code == 404
    assert r.status_code != 401


def test_health_requires_no_key():
    """Health checks must never require authentication."""
    r = requests.get(f"{BASE_URL}/health", timeout=10)
    assert r.status_code == 200
