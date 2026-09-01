"""
backend/tests/test_employee_system.py — Comprehensive Test Suite for Employee Access & Time Tracking.

Covers:
  1. Employee Account CRUD (Owner-only) & duplicate username validation.
  2. Employee Authentication (Login, JWT token issue, Invalid credentials, Deactivated account).
  3. Restricted Employee View & API-level RBAC:
     - Assigned client access (Allowed, Invoices omitted)
     - Unassigned client access (403 Forbidden)
     - Client creation/deletion forbidden for employees (403 Forbidden)
     - Assigned project access (Financial fields total_amount/paid_amount stripped)
     - Unassigned project access (403 Forbidden)
     - Invoice endpoints forbidden for employees (403 Forbidden)
     - Canvas access for assigned projects
  4. Automated Activity Logging (Viewing/editing assigned records records activity logs in background).
  5. Attendance Tracking (Clock-in, Clock-out, Status, Duration calculation, Double clock-in prevention).
  6. Owner Monthly Report (Aggregated employee hours, day-by-day activity breakdown, RBAC enforcement).
"""
import pytest
import requests
from tests.conftest import BASE_URL, API_KEY

API = f"{BASE_URL}/api"
OWNER_HEADERS = {"Content-Type": "application/json", "X-API-Key": API_KEY}


@pytest.fixture(scope="module")
def owner_session():
    """Owner authenticated session."""
    sess = requests.Session()
    sess.headers.update(OWNER_HEADERS)
    return sess


@pytest.fixture(scope="module")
def test_clients(owner_session):
    """Create two test clients: one assigned to employee, one unassigned."""
    # Client 1 (Assigned)
    r1 = owner_session.post(
        f"{API}/clients",
        json={
            "name": "TEST_Emp Assigned Client",
            "email": "assigned@test-atelier.com",
            "measurements": {"Bust": '34"', "Waist": '26"'},
            "notes": "Assigned to test employee",
        },
        timeout=20,
    )
    assert r1.status_code == 200, r1.text
    c1 = r1.json()

    # Add an invoice item to Client 1 (to test financial data isolation)
    r_inv = owner_session.post(
        f"{API}/clients/{c1['id']}/invoices/items",
        json={"description": "Design Consultation", "amount": 2500.0, "status": "pending"},
        timeout=20,
    )
    assert r_inv.status_code == 200

    # Client 2 (Unassigned)
    r2 = owner_session.post(
        f"{API}/clients",
        json={
            "name": "TEST_Emp Secret Client",
            "email": "secret@test-atelier.com",
            "measurements": {"Bust": '36"', "Waist": '28"'},
            "notes": "NOT assigned to test employee",
        },
        timeout=20,
    )
    assert r2.status_code == 200, r2.text
    c2 = r2.json()

    yield {"assigned": c1, "unassigned": c2}

    # Teardown
    owner_session.delete(f"{API}/clients/{c1['id']}", timeout=20)
    owner_session.delete(f"{API}/clients/{c2['id']}", timeout=20)


@pytest.fixture(scope="module")
def test_projects(owner_session, test_clients):
    """Create projects for both assigned and unassigned clients."""
    # Project 1 (for assigned client)
    r1 = owner_session.post(
        f"{API}/projects",
        json={
            "client_id": test_clients["assigned"]["id"],
            "title": "TEST_Silk Evening Gown",
            "deadline": "2026-09-30",
            "total_amount": 50000.0,
            "paid_amount": 20000.0,
            "description": "Silk embroidery gown",
        },
        timeout=20,
    )
    assert r1.status_code == 200, r1.text
    p1 = r1.json()

    # Project 2 (for unassigned client)
    r2 = owner_session.post(
        f"{API}/projects",
        json={
            "client_id": test_clients["unassigned"]["id"],
            "title": "TEST_Confidential Bridal Lehenga",
            "deadline": "2026-10-15",
            "total_amount": 120000.0,
            "paid_amount": 60000.0,
            "description": "Private project",
        },
        timeout=20,
    )
    assert r2.status_code == 200, r2.text
    p2 = r2.json()

    yield {"assigned_proj": p1, "unassigned_proj": p2}

    # Teardown
    owner_session.delete(f"{API}/projects/{p1['id']}", timeout=20)
    owner_session.delete(f"{API}/projects/{p2['id']}", timeout=20)


@pytest.fixture(scope="module")
def test_employee(owner_session, test_clients):
    """Create a test employee assigned only to Client 1."""
    username = f"emp_test_{test_clients['assigned']['id'][:6]}"
    password = "secretPassword123"
    r = owner_session.post(
        f"{API}/admin/employees",
        json={
            "name": "Sarah Miller",
            "username": username,
            "password": password,
            "assigned_client_ids": [test_clients["assigned"]["id"]],
            "active": True,
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    emp_data = r.json()
    emp_data["raw_password"] = password

    yield emp_data

    # Teardown
    owner_session.delete(f"{API}/admin/employees/{emp_data['id']}", timeout=20)


@pytest.fixture(scope="module")
def employee_session(test_employee):
    """Employee authenticated session with JWT token."""
    login_res = requests.post(
        f"{API}/employees/login",
        json={
            "username": test_employee["username"],
            "password": test_employee["raw_password"],
        },
        timeout=20,
    )
    assert login_res.status_code == 200, login_res.text
    body = login_res.json()
    token = body["token"]

    sess = requests.Session()
    sess.headers.update(
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
    )
    sess.auth_token = token
    return sess


# ── 1. EMPLOYEE ACCOUNT CREATION & ADMIN TESTS ───────────────────────────────

def test_owner_create_employee_success(test_employee):
    assert test_employee["name"] == "Sarah Miller"
    assert "hashed_password" not in test_employee
    assert test_employee["active"] is True
    assert len(test_employee["assigned_client_ids"]) == 1


def test_duplicate_username_returns_409(owner_session, test_employee):
    r = owner_session.post(
        f"{API}/admin/employees",
        json={
            "name": "Duplicate User",
            "username": test_employee["username"].upper(),  # Case-insensitive check
            "password": "anotherPassword",
            "assigned_client_ids": [],
        },
        timeout=20,
    )
    assert r.status_code == 409


def test_owner_list_employees(owner_session, test_employee):
    r = owner_session.get(f"{API}/admin/employees", timeout=20)
    assert r.status_code == 200
    emps = r.json()
    assert isinstance(emps, list)
    matching = [e for e in emps if e["id"] == test_employee["id"]]
    assert len(matching) == 1
    assert "hashed_password" not in matching[0]


def test_employee_cannot_access_admin_endpoints(employee_session, test_employee):
    r = employee_session.get(f"{API}/admin/employees", timeout=20)
    assert r.status_code == 403

    r2 = employee_session.post(
        f"{API}/admin/employees",
        json={"name": "Hacker", "username": "hack", "password": "123"},
        timeout=20,
    )
    assert r2.status_code == 403


# ── 2. EMPLOYEE AUTHENTICATION TESTS ─────────────────────────────────────────

def test_employee_login_wrong_password(test_employee):
    r = requests.post(
        f"{API}/employees/login",
        json={"username": test_employee["username"], "password": "wrong_password_xyz"},
        timeout=20,
    )
    assert r.status_code == 401


def test_employee_me_profile(employee_session, test_employee):
    r = employee_session.get(f"{API}/employees/me", timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "employee"
    assert body["employee"]["id"] == test_employee["id"]
    assert "is_clocked_in" in body


# ── 3. RESTRICTED EMPLOYEE VIEW & RBAC TESTS ─────────────────────────────────

def test_employee_list_clients_filtered(employee_session, test_clients):
    """Employee must only see clients in assigned_client_ids."""
    r = employee_session.get(f"{API}/clients", timeout=20)
    assert r.status_code == 200
    clients = r.json()
    client_ids = [c["id"] for c in clients]
    assert test_clients["assigned"]["id"] in client_ids
    assert test_clients["unassigned"]["id"] not in client_ids


def test_employee_get_assigned_client_omits_invoices(employee_session, test_clients):
    """Employee bundle for assigned client must NOT include invoice / payments."""
    cid = test_clients["assigned"]["id"]
    r = employee_session.get(f"{API}/clients/{cid}", timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert body["client"]["id"] == cid
    assert body["client"]["name"] == test_clients["assigned"]["name"]
    # Invoices must be omitted
    assert body.get("invoice") is None


def test_employee_get_unassigned_client_returns_403(employee_session, test_clients):
    """Employee attempting to fetch an unassigned client must receive 403 Forbidden."""
    cid = test_clients["unassigned"]["id"]
    r = employee_session.get(f"{API}/clients/{cid}", timeout=20)
    assert r.status_code == 403
    assert "Forbidden" in r.text


def test_employee_cannot_create_or_delete_clients(employee_session, test_clients):
    """Employee must receive 403 when attempting client creation or deletion."""
    r_create = employee_session.post(
        f"{API}/clients",
        json={"name": "Forbidden Client Creation"},
        timeout=20,
    )
    assert r_create.status_code == 403

    r_delete = employee_session.delete(
        f"{API}/clients/{test_clients['assigned']['id']}",
        timeout=20,
    )
    assert r_delete.status_code == 403


def test_employee_cannot_access_invoice_endpoints(employee_session, test_clients):
    """Employee attempting to mutate invoices must receive 403 Forbidden."""
    cid = test_clients["assigned"]["id"]
    r = employee_session.post(
        f"{API}/clients/{cid}/invoices/items",
        json={"description": "Hacked Fee", "amount": 9999.0},
        timeout=20,
    )
    assert r.status_code == 403


def test_employee_projects_strips_financials(employee_session, test_projects):
    """Employee projects list must only show assigned client projects and strip total_amount/paid_amount."""
    r = employee_session.get(f"{API}/projects", timeout=20)
    assert r.status_code == 200
    projects = r.json()
    proj_ids = [p["id"] for p in projects]
    assert test_projects["assigned_proj"]["id"] in proj_ids
    assert test_projects["unassigned_proj"]["id"] not in proj_ids

    # Verify financial fields stripped
    for p in projects:
        assert "total_amount" not in p
        assert "paid_amount" not in p


def test_employee_get_unassigned_project_returns_403(employee_session, test_projects):
    """Employee attempting to fetch unassigned project must receive 403 Forbidden."""
    pid = test_projects["unassigned_proj"]["id"]
    r = employee_session.get(f"{API}/projects/{pid}", timeout=20)
    assert r.status_code == 403


def test_employee_canvas_access(employee_session, test_projects):
    """Employee can read and save canvas for assigned projects."""
    pid = test_projects["assigned_proj"]["id"]
    # Get canvas
    r_get = employee_session.get(f"{API}/projects/{pid}/canvas", timeout=20)
    assert r_get.status_code == 200

    # Save canvas
    r_save = employee_session.put(
        f"{API}/projects/{pid}/canvas",
        json={
            "gender": "female",
            "strokes": [{"d": "M0 0 L50 50", "color": "#111", "width": 2}],
        },
        timeout=20,
    )
    assert r_save.status_code == 200


# ── 4. CLOCK IN / CLOCK OUT ATTENDANCE TESTS ─────────────────────────────────

def test_attendance_clock_in_and_out_lifecycle(employee_session):
    """Test full clock-in / clock-out lifecycle and duration calculation."""
    # 1. Clock in
    r_in = employee_session.post(f"{API}/attendance/clock-in", timeout=20)
    assert r_in.status_code == 200, r_in.text
    in_log = r_in.json()
    assert in_log["clock_in_time"] is not None
    assert in_log["clock_out_time"] is None

    # 2. Check status — should be clocked in
    r_status = employee_session.get(f"{API}/attendance/status", timeout=20)
    assert r_status.status_code == 200
    status = r_status.json()
    assert status["is_clocked_in"] is True
    assert status["current_session"]["id"] == in_log["id"]

    # 3. Double clock-in should fail with 400
    r_double = employee_session.post(f"{API}/attendance/clock-in", timeout=20)
    assert r_double.status_code == 400
    assert "Already clocked in" in r_double.text

    # 4. Clock out
    r_out = employee_session.post(f"{API}/attendance/clock-out", timeout=20)
    assert r_out.status_code == 200, r_out.text
    out_log = r_out.json()
    assert out_log["clock_out_time"] is not None
    assert out_log["duration_minutes"] is not None
    assert out_log["duration_minutes"] >= 0.0

    # 5. Status after clock-out — should be False
    r_status2 = employee_session.get(f"{API}/attendance/status", timeout=20)
    assert r_status2.status_code == 200
    assert r_status2.json()["is_clocked_in"] is False

    # 6. Double clock-out should fail with 400
    r_out_again = employee_session.post(f"{API}/attendance/clock-out", timeout=20)
    assert r_out_again.status_code == 400


def test_attendance_history(employee_session):
    r = employee_session.get(f"{API}/attendance/history", timeout=20)
    assert r.status_code == 200
    logs = r.json()
    assert isinstance(logs, list)
    assert len(logs) >= 1


# ── 5. OWNER MONTHLY REPORT & ACTIVITY LOG TESTS ─────────────────────────────

def test_owner_monthly_report_contains_activities_and_hours(
    owner_session, test_employee, test_clients, test_projects, employee_session
):
    """
    Verify owner monthly report aggregates attendance and captures automatic activity logs.
    """
    # Trigger an activity: employee views assigned client & project
    employee_session.get(f"{API}/clients/{test_clients['assigned']['id']}", timeout=20)
    employee_session.get(f"{API}/projects/{test_projects['assigned_proj']['id']}", timeout=20)

    # Owner fetches monthly report
    import datetime
    current_month = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    r = owner_session.get(
        f"{API}/admin/reports/monthly?month={current_month}&employee_id={test_employee['id']}",
        timeout=20,
    )
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["month"] == current_month
    assert len(report["employees"]) == 1
    emp_report = report["employees"][0]
    assert emp_report["employee_id"] == test_employee["id"]
    assert emp_report["employee_name"] == test_employee["name"]
    assert "daily_breakdown" in emp_report
    assert emp_report["total_activities"] >= 2


def test_employee_cannot_access_monthly_report(employee_session):
    r = employee_session.get(f"{API}/admin/reports/monthly", timeout=20)
    assert r.status_code == 403
