"""
backend/tests/test_salary.py — Test Suite for Salary Tracking (Owner-Only).

Covers:
  1. Owner can set a salary record (upsert amount_due for a month).
  2. Owner can record payments and computed status changes correctly.
  3. Owner can get salary history for an employee.
  4. Owner can get a monthly salary summary across all employees.
  5. Employee CANNOT access any salary endpoint (403 Forbidden).
"""
import pytest
import requests
from tests.conftest import BASE_URL, API_KEY

API = f"{BASE_URL}/api"
OWNER_HEADERS = {"Content-Type": "application/json", "X-API-Key": API_KEY}


@pytest.fixture(scope="module")
def owner_session():
    sess = requests.Session()
    sess.headers.update(OWNER_HEADERS)
    return sess


@pytest.fixture(scope="module")
def setup_data(owner_session):
    """Create an employee for salary testing."""
    r = owner_session.post(f"{API}/admin/employees", json={
        "name": "Salary Worker",
        "username": "salary_worker",
        "password": "testpass123",
        "assigned_client_ids": [],
        "active": True,
    }, timeout=20)
    assert r.status_code == 200, f"Failed to create employee: {r.text}"
    emp = r.json()

    yield {"emp": emp}

    # Teardown
    owner_session.delete(f"{API}/admin/employees/{emp['id']}", timeout=20)


@pytest.fixture(scope="module")
def employee_session(setup_data):
    """Employee authenticated session with JWT token."""
    login_res = requests.post(
        f"{API}/employees/login",
        json={"username": "salary_worker", "password": "testpass123"},
        timeout=20,
    )
    assert login_res.status_code == 200, f"Employee login failed: {login_res.text}"
    token = login_res.json()["token"]
    sess = requests.Session()
    sess.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    })
    return sess


# ── 1. OWNER SET SALARY ─────────────────────────────────────────────────────

def test_owner_set_salary(owner_session, setup_data):
    """Owner can set amount_due for a month."""
    e_id = setup_data["emp"]["id"]
    r = owner_session.post(
        f"{API}/employees/{e_id}/salary?month=2026-08",
        json={"amount_due": 5000},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["amount_due"] == 5000
    assert data["status"] == "unpaid"
    assert data["employee_id"] == e_id
    assert data["month"] == "2026-08"


# ── 2. OWNER RECORD PAYMENTS ────────────────────────────────────────────────

def test_owner_record_partial_then_full_payment(owner_session, setup_data):
    """Recording payments should transition status: unpaid → partially_paid → paid."""
    e_id = setup_data["emp"]["id"]

    # Partial payment
    r1 = owner_session.post(
        f"{API}/employees/{e_id}/salary/payment?month=2026-08",
        json={"amount": 2000, "date": "2026-08-15", "note": "First installment"},
        timeout=20,
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "partially_paid"

    # Full payment
    r2 = owner_session.post(
        f"{API}/employees/{e_id}/salary/payment?month=2026-08",
        json={"amount": 3000, "date": "2026-08-30"},
        timeout=20,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "paid"


# ── 3. OWNER SALARY HISTORY ─────────────────────────────────────────────────

def test_owner_salary_history(owner_session, setup_data):
    """Owner can retrieve salary history for an employee."""
    e_id = setup_data["emp"]["id"]
    r = owner_session.get(f"{API}/employees/{e_id}/salary", timeout=20)
    assert r.status_code == 200, r.text
    records = r.json()
    assert isinstance(records, list)
    assert len(records) >= 1
    assert records[0]["month"] == "2026-08"


# ── 4. OWNER SALARY SUMMARY ─────────────────────────────────────────────────

def test_owner_salary_summary(owner_session, setup_data):
    """Owner can get a monthly summary of all employees' salaries."""
    r = owner_session.get(f"{API}/salary/summary?month=2026-08", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["month"] == "2026-08"
    summary = data["summary"]
    assert isinstance(summary, list)

    emp_record = next(
        (x for x in summary if x["employee_id"] == setup_data["emp"]["id"]), None
    )
    assert emp_record is not None, "Employee should appear in salary summary"
    assert emp_record["amount_due"] == 5000
    assert emp_record["total_paid"] == 5000
    assert emp_record["status"] == "paid"


# ── 5. EMPLOYEE CANNOT ACCESS ANY SALARY ENDPOINT ───────────────────────────

def test_employee_cannot_access_salary_set(employee_session, setup_data):
    """Employee must get 403 when trying to set salary."""
    e_id = setup_data["emp"]["id"]
    r = employee_session.post(
        f"{API}/employees/{e_id}/salary?month=2026-08",
        json={"amount_due": 5000},
        timeout=20,
    )
    assert r.status_code == 403


def test_employee_cannot_access_salary_payment(employee_session, setup_data):
    """Employee must get 403 when trying to record a payment."""
    e_id = setup_data["emp"]["id"]
    r = employee_session.post(
        f"{API}/employees/{e_id}/salary/payment?month=2026-08",
        json={"amount": 1000, "date": "2026-08-15"},
        timeout=20,
    )
    assert r.status_code == 403


def test_employee_cannot_access_salary_history(employee_session, setup_data):
    """Employee must get 403 when trying to view salary history — even their own."""
    e_id = setup_data["emp"]["id"]
    r = employee_session.get(f"{API}/employees/{e_id}/salary", timeout=20)
    assert r.status_code == 403


def test_employee_cannot_access_salary_summary(employee_session, setup_data):
    """Employee must get 403 when trying to view salary summary."""
    r = employee_session.get(f"{API}/salary/summary?month=2026-08", timeout=20)
    assert r.status_code == 403
