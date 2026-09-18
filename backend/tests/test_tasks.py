"""
backend/tests/test_tasks.py — Test Suite for Per-Project Employee Task Checklist.

Covers:
  1. Owner can create, list, and delete tasks.
  2. Employee cannot create tasks (403).
  3. Employee can only see their own tasks on assigned-client projects.
  4. Employee cannot access tasks on unassigned-client projects (403).
  5. Employee can update status of their own tasks (but not title/reassign).
  6. Employee cannot update another employee's tasks (403).
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
    """Create clients, employees, and projects for testing tasks."""
    # Create client 1 (assigned) and client 2 (unassigned)
    r1 = owner_session.post(f"{API}/clients", json={"name": "TaskTest Client A"}, timeout=20)
    assert r1.status_code == 200, f"Failed to create client A: {r1.text}"
    c1 = r1.json()

    r2 = owner_session.post(f"{API}/clients", json={"name": "TaskTest Client B"}, timeout=20)
    assert r2.status_code == 200, f"Failed to create client B: {r2.text}"
    c2 = r2.json()

    # Create employee 1 assigned to client 1
    r_emp1 = owner_session.post(f"{API}/admin/employees", json={
        "name": "Task Worker 1",
        "username": "task_worker_1",
        "password": "testpass123",
        "assigned_client_ids": [c1["id"]],
        "active": True,
    }, timeout=20)
    assert r_emp1.status_code == 200, f"Failed to create employee 1: {r_emp1.text}"
    emp1 = r_emp1.json()

    # Create employee 2 also assigned to client 1 (for cross-employee visibility tests)
    r_emp2 = owner_session.post(f"{API}/admin/employees", json={
        "name": "Task Worker 2",
        "username": "task_worker_2",
        "password": "testpass123",
        "assigned_client_ids": [c1["id"]],
        "active": True,
    }, timeout=20)
    assert r_emp2.status_code == 200, f"Failed to create employee 2: {r_emp2.text}"
    emp2 = r_emp2.json()

    # Create projects for both clients
    r_p1 = owner_session.post(f"{API}/projects", json={
        "client_id": c1["id"], "title": "TaskTest Project A",
    }, timeout=20)
    assert r_p1.status_code == 200, f"Failed to create project A: {r_p1.text}"
    p1 = r_p1.json()

    r_p2 = owner_session.post(f"{API}/projects", json={
        "client_id": c2["id"], "title": "TaskTest Project B",
    }, timeout=20)
    assert r_p2.status_code == 200, f"Failed to create project B: {r_p2.text}"
    p2 = r_p2.json()

    yield {"emp1": emp1, "emp2": emp2, "c1": c1, "c2": c2, "p1": p1, "p2": p2}

    # Teardown
    owner_session.delete(f"{API}/admin/employees/{emp1['id']}", timeout=20)
    owner_session.delete(f"{API}/admin/employees/{emp2['id']}", timeout=20)
    owner_session.delete(f"{API}/projects/{p1['id']}", timeout=20)
    owner_session.delete(f"{API}/projects/{p2['id']}", timeout=20)
    owner_session.delete(f"{API}/clients/{c1['id']}", timeout=20)
    owner_session.delete(f"{API}/clients/{c2['id']}", timeout=20)


@pytest.fixture(scope="module")
def employee_session(setup_data):
    """Employee 1 authenticated session with JWT token."""
    login_res = requests.post(
        f"{API}/employees/login",
        json={"username": "task_worker_1", "password": "testpass123"},
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


# ── 1. OWNER TASK CRUD ───────────────────────────────────────────────────────

def test_owner_create_and_list_tasks(owner_session, setup_data):
    """Owner can create a task and list it."""
    p_id = setup_data["p1"]["id"]
    e_id = setup_data["emp1"]["id"]

    r = owner_session.post(f"{API}/projects/{p_id}/tasks", json={
        "title": "Design initial sketch",
        "assigned_employee_id": e_id,
    }, timeout=20)
    assert r.status_code == 200, r.text
    task = r.json()
    assert task["title"] == "Design initial sketch"
    assert task["status"] == "pending"
    assert task["assigned_employee_id"] == e_id
    assert task["project_id"] == p_id

    # List tasks
    r_list = owner_session.get(f"{API}/projects/{p_id}/tasks", timeout=20)
    assert r_list.status_code == 200
    tasks = r_list.json()
    assert any(t["id"] == task["id"] for t in tasks)

    # Cleanup
    owner_session.delete(f"{API}/tasks/{task['id']}", timeout=20)


def test_owner_delete_task(owner_session, setup_data):
    """Owner can delete a task."""
    p_id = setup_data["p1"]["id"]
    e_id = setup_data["emp1"]["id"]

    t = owner_session.post(f"{API}/projects/{p_id}/tasks", json={
        "title": "Temp task", "assigned_employee_id": e_id,
    }, timeout=20).json()

    r = owner_session.delete(f"{API}/tasks/{t['id']}", timeout=20)
    assert r.status_code == 204


# ── 2. EMPLOYEE CANNOT CREATE TASKS ──────────────────────────────────────────

def test_employee_cannot_create_tasks(employee_session, setup_data):
    """Employee must receive 403 when attempting to create a task."""
    p_id = setup_data["p1"]["id"]
    e_id = setup_data["emp1"]["id"]
    r = employee_session.post(f"{API}/projects/{p_id}/tasks", json={
        "title": "Unauthorized task",
        "assigned_employee_id": e_id,
    }, timeout=20)
    assert r.status_code == 403


# ── 3. EMPLOYEE TASK VISIBILITY (only own tasks) ────────────────────────────

def test_employee_sees_only_own_tasks(owner_session, employee_session, setup_data):
    """Employee should only see tasks assigned to them, not other employees' tasks."""
    p_id = setup_data["p1"]["id"]
    e1_id = setup_data["emp1"]["id"]
    e2_id = setup_data["emp2"]["id"]

    # Owner creates tasks for both employees
    t1 = owner_session.post(f"{API}/projects/{p_id}/tasks", json={
        "title": "Task for emp1", "assigned_employee_id": e1_id,
    }, timeout=20).json()
    t2 = owner_session.post(f"{API}/projects/{p_id}/tasks", json={
        "title": "Task for emp2", "assigned_employee_id": e2_id,
    }, timeout=20).json()

    # emp1 lists tasks -> should only see t1
    r = employee_session.get(f"{API}/projects/{p_id}/tasks", timeout=20)
    assert r.status_code == 200
    tasks = r.json()
    task_ids = [t["id"] for t in tasks]
    assert t1["id"] in task_ids, "Employee should see their own task"
    assert t2["id"] not in task_ids, "Employee should NOT see another employee's task"

    # Cleanup
    owner_session.delete(f"{API}/tasks/{t1['id']}", timeout=20)
    owner_session.delete(f"{API}/tasks/{t2['id']}", timeout=20)


# ── 4. EMPLOYEE CANNOT ACCESS UNASSIGNED PROJECT TASKS ──────────────────────

def test_employee_cannot_access_unassigned_project_tasks(employee_session, setup_data):
    """Employee accessing tasks on a project whose client they're not assigned to → 403."""
    p_id = setup_data["p2"]["id"]  # Project B belongs to Client B (unassigned)
    r = employee_session.get(f"{API}/projects/{p_id}/tasks", timeout=20)
    assert r.status_code == 403


# ── 5. EMPLOYEE STATUS UPDATE ───────────────────────────────────────────────

def test_employee_update_task_status(owner_session, employee_session, setup_data):
    """Employee can update status of their own task but cannot change title."""
    p_id = setup_data["p1"]["id"]
    e_id = setup_data["emp1"]["id"]

    t = owner_session.post(f"{API}/projects/{p_id}/tasks", json={
        "title": "Status test task", "assigned_employee_id": e_id,
    }, timeout=20).json()

    # Employee updates status to in_progress
    r = employee_session.put(f"{API}/tasks/{t['id']}", json={
        "status": "in_progress",
    }, timeout=20)
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"

    # Employee tries to update title (should be ignored, only status changes)
    r2 = employee_session.put(f"{API}/tasks/{t['id']}", json={
        "title": "Hacked Title",
        "status": "completed",
    }, timeout=20)
    assert r2.status_code == 200
    assert r2.json()["title"] == "Status test task", "Title should NOT change for employee"
    assert r2.json()["status"] == "completed"
    assert r2.json()["completed_at"] is not None, "completed_at should be set"

    # Cleanup
    owner_session.delete(f"{API}/tasks/{t['id']}", timeout=20)


# ── 6. EMPLOYEE CANNOT UPDATE OTHER EMPLOYEE'S TASKS ────────────────────────

def test_employee_cannot_update_others_tasks(owner_session, employee_session, setup_data):
    """Employee attempting to update another employee's task → 403."""
    p_id = setup_data["p1"]["id"]
    e2_id = setup_data["emp2"]["id"]

    t = owner_session.post(f"{API}/projects/{p_id}/tasks", json={
        "title": "Task for emp2 only", "assigned_employee_id": e2_id,
    }, timeout=20).json()

    r = employee_session.put(f"{API}/tasks/{t['id']}", json={
        "status": "completed",
    }, timeout=20)
    assert r.status_code == 403

    # Cleanup
    owner_session.delete(f"{API}/tasks/{t['id']}", timeout=20)
