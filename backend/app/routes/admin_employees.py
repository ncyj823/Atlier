"""
app/routes/admin_employees.py — Owner-only Employee Account Administration.

Endpoints:
  GET    /api/admin/employees               — List all employees
  POST   /api/admin/employees               — Create new employee
  GET    /api/admin/employees/{employee_id} — Get employee details
  PUT    /api/admin/employees/{employee_id} — Update employee details/permissions
  DELETE /api/admin/employees/{employee_id} — Delete / deactivate employee
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import AuthContext, hash_password, require_owner
from app.database import db
from app.models.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin_employees"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/admin/employees", response_model=List[EmployeeOut])
async def list_employees(auth: AuthContext = Depends(require_owner)):
    """List all employees (Owner only)."""
    cursor = db.employees.find({}, {"_id": 0, "hashed_password": 0}).sort("created_at", -1)
    return [EmployeeOut(**d) async for d in cursor]


@router.post("/admin/employees", response_model=EmployeeOut)
async def create_employee(
    payload: EmployeeCreate,
    auth: AuthContext = Depends(require_owner),
):
    """Create a new employee account with hashed password and assigned client IDs."""
    clean_username = payload.username.strip()
    if not clean_username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")

    # Check for duplicate username (case-insensitive)
    existing = await db.employees.find_one(
        {"username": {"$regex": f"^{re.escape(clean_username)}$", "$options": "i"}},
        {"_id": 0, "id": 1},
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{clean_username}' is already taken",
        )

    # Validate that assigned client IDs exist (optional, non-blocking check)
    assigned_ids = payload.assigned_client_ids or []

    now = _now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "name": payload.name.strip(),
        "username": clean_username,
        "hashed_password": hash_password(payload.password),
        "assigned_client_ids": assigned_ids,
        "active": payload.active,
        "created_at": now,
        "updated_at": now,
    }

    await db.employees.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("hashed_password", None)
    return EmployeeOut(**doc)


@router.get("/admin/employees/{employee_id}", response_model=EmployeeOut)
async def get_employee(
    employee_id: str,
    auth: AuthContext = Depends(require_owner),
):
    """Get single employee details."""
    emp = await db.employees.find_one(
        {"id": employee_id},
        {"_id": 0, "hashed_password": 0},
    )
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return EmployeeOut(**emp)


@router.put("/admin/employees/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: str,
    payload: EmployeeUpdate,
    auth: AuthContext = Depends(require_owner),
):
    """
    Update employee account details, password, status, or assigned clients.
    """
    emp = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    update_dict = {}

    if payload.name is not None:
        update_dict["name"] = payload.name.strip()

    if payload.username is not None:
        clean_user = payload.username.strip()
        if not clean_user:
            raise HTTPException(status_code=400, detail="Username cannot be empty")
        # Check uniqueness if username is changing
        if clean_user.lower() != emp["username"].lower():
            dup = await db.employees.find_one(
                {
                    "username": {"$regex": f"^{re.escape(clean_user)}$", "$options": "i"},
                    "id": {"$ne": employee_id},
                },
                {"_id": 0, "id": 1},
            )
            if dup:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Username '{clean_user}' is already taken",
                )
        update_dict["username"] = clean_user

    if payload.password is not None and payload.password.strip():
        if len(payload.password.strip()) < 4:
            raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
        update_dict["hashed_password"] = hash_password(payload.password.strip())

    if payload.assigned_client_ids is not None:
        update_dict["assigned_client_ids"] = payload.assigned_client_ids

    if payload.active is not None:
        update_dict["active"] = payload.active

    if not update_dict:
        emp.pop("hashed_password", None)
        return EmployeeOut(**emp)

    update_dict["updated_at"] = _now_iso()

    res = await db.employees.find_one_and_update(
        {"id": employee_id},
        {"$set": update_dict},
        projection={"_id": 0, "hashed_password": 0},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Employee not found")
    return EmployeeOut(**res)


@router.delete("/admin/employees/{employee_id}")
async def delete_employee(
    employee_id: str,
    auth: AuthContext = Depends(require_owner),
):
    """Delete an employee account and their active session (Owner only)."""
    res = await db.employees.delete_one({"id": employee_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"ok": True, "deleted_id": employee_id}
