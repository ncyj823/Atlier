"""
app/routes/employee_auth.py — Employee Login and Self Profile routes.

Endpoints:
  POST /api/employees/login — Authenticate employee with username + password
  GET  /api/employees/me    — Get current employee profile and clock-in status
"""
import logging
import re
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import (
    AuthContext,
    create_access_token,
    get_current_auth,
    verify_password,
)
from app.database import db
from app.models.employee import EmployeeLogin, EmployeeLoginOut, EmployeeOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["employee_auth"])


@router.post("/employees/login", response_model=EmployeeLoginOut)
async def employee_login(payload: EmployeeLogin):
    """
    Employee login with username and password.
    Returns signed JWT access token and employee profile.
    """
    clean_username = payload.username.strip()
    if not clean_username or not payload.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required",
        )

    # Case-insensitive username lookup
    emp = await db.employees.find_one(
        {"username": {"$regex": f"^{re.escape(clean_username)}$", "$options": "i"}},
        {"_id": 0},
    )

    if not emp or not verify_password(payload.password, emp.get("hashed_password", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not emp.get("active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee account is deactivated. Please contact the owner.",
        )

    token = create_access_token(
        data={
            "sub": emp["id"],
            "employee_id": emp["id"],
            "username": emp["username"],
            "role": "employee",
        }
    )

    emp_out = EmployeeOut(
        id=emp["id"],
        name=emp["name"],
        username=emp["username"],
        assigned_client_ids=emp.get("assigned_client_ids", []),
        active=emp.get("active", True),
        created_at=emp.get("created_at", ""),
        updated_at=emp.get("updated_at"),
    )

    return EmployeeLoginOut(token=token, employee=emp_out)


@router.get("/employees/me")
async def get_current_user_profile(auth: AuthContext = Depends(get_current_auth)):
    """
    Get profile information and current clock-in session for the authenticated user.
    """
    if auth.is_owner:
        return {"role": "owner", "is_owner": True}

    emp = await db.employees.find_one({"id": auth.employee_id}, {"_id": 0, "hashed_password": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    active_session = await db.attendance_logs.find_one(
        {"employee_id": auth.employee_id, "clock_out_time": None},
        {"_id": 0},
    )

    return {
        "role": "employee",
        "employee": EmployeeOut(
            id=emp["id"],
            name=emp["name"],
            username=emp["username"],
            assigned_client_ids=emp.get("assigned_client_ids", []),
            active=emp.get("active", True),
            created_at=emp.get("created_at", ""),
            updated_at=emp.get("updated_at"),
        ),
        "is_clocked_in": bool(active_session),
        "current_session": active_session,
    }
