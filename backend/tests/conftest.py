"""
tests/conftest.py — Shared pytest fixtures for the Atelier API test suite.

Tests run against a live backend. Set ATELIER_TEST_URL and ATELIER_TEST_API_KEY
in the environment (or .env) before running. Defaults to localhost:8000.

Usage:
    cd backend
    ATELIER_TEST_URL=http://localhost:8000 ATELIER_TEST_API_KEY=my_key pytest tests/ -v
"""
import os
import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

# Load .env from backend/ directory so tests can read API_KEY
load_dotenv(Path(__file__).parent.parent / ".env")

BASE_URL = os.environ.get(
    "ATELIER_TEST_URL",
    os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8000"),
).rstrip("/")

API_KEY = os.environ.get(
    "ATELIER_TEST_API_KEY",
    os.environ.get("API_KEY", ""),
)

API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def api_url() -> str:
    return API


@pytest.fixture(scope="session")
def s() -> requests.Session:
    """Authenticated session — includes X-API-Key header."""
    sess = requests.Session()
    sess.headers.update(
        {"Content-Type": "application/json", "X-API-Key": API_KEY}
    )
    return sess


@pytest.fixture(scope="session")
def anon() -> requests.Session:
    """Unauthenticated session — no API key header."""
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="session")
def seeded(s, api_url):
    """Ensure demo data exists (idempotent)."""
    r = s.post(f"{api_url}/_seed", timeout=20)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="session")
def demo_client_id(s, api_url, seeded):
    """Return the ID of the first seeded client."""
    r = s.get(f"{api_url}/clients", timeout=20)
    assert r.status_code == 200
    clients = r.json()
    assert clients, "Expected at least one seeded client"
    return clients[0]["id"]
