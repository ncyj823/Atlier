"""
app/routes/attendance.py — Employee Clock-in / Clock-out Attendance Tracking.

Endpoints:
  POST /api/attendance/clock-in  — Clock in (starts new session; one active per employee)
  POST /api/attendance/clock-out — Clock out (closes active session, computes duration)
  GET  /api/attendance/status    — Get current status and today's total time
  GET  /api/attendance/history   — Get attendance history for employee
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from dateutil import parser as date_parser
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import AuthContext, require_auth, require_employee
from app.database import db
from app.models.attendance import AttendanceLog, AttendanceStatusOut
from app.services.activity_logger import log_employee_activity

logger = logging.getLogger(__name__)
router = APIRouter(tags=["attendance"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/attendance/clock-in", response_model=AttendanceLog)
async def clock_in(auth: AuthContext = Depends(require_employee)):
    """
    Clock in for the current employee.
    Enforces at most one active (unclosed) session per employee.
    """
    existing = await db.attendance_logs.find_one(
        {"employee_id": auth.employee_id, "clock_out_time": None},
        {"_id": 0},
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Already clocked in since {existing['clock_in_time']}",
        )

    now = _now_utc()
    doc = {
        "id": str(uuid.uuid4()),
        "employee_id": auth.employee_id,
        "employee_name": auth.name or auth.username or "",
        "clock_in_time": now.isoformat(),
        "clock_out_time": None,
        "date": now.strftime("%Y-%m-%d"),
        "duration_minutes": None,
        "created_at": now.isoformat(),
    }

    await db.attendance_logs.insert_one(doc)
    doc.pop("_id", None)

    await log_employee_activity(
        auth=auth,
        entity_type="attendance",
        entity_id=doc["id"],
        action="clocked in",
        details="Started work session",
    )

    return AttendanceLog(**doc)


@router.post("/attendance/clock-out", response_model=AttendanceLog)
async def clock_out(auth: AuthContext = Depends(require_employee)):
    """
    Clock out for the current employee.
    Closes the open session and computes duration in minutes.
    """
    existing = await db.attendance_logs.find_one(
        {"employee_id": auth.employee_id, "clock_out_time": None},
        {"_id": 0},
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active clock-in session found to clock out from.",
        )

    now = _now_utc()
    try:
        in_time = date_parser.isoparse(existing["clock_in_time"])
        if in_time.tzinfo is None:
            in_time = in_time.replace(tzinfo=timezone.utc)
        duration_mins = max(0.0, round((now - in_time).total_seconds() / 60.0, 2))
    except Exception as exc:
        logger.warning("Failed to compute duration: %s", exc)
        duration_mins = 0.0

    res = await db.attendance_logs.find_one_and_update(
        {"id": existing["id"]},
        {
            "$set": {
                "clock_out_time": now.isoformat(),
                "duration_minutes": duration_mins,
            }
        },
        projection={"_id": 0},
        return_document=True,
    )

    hours = round(duration_mins / 60.0, 2)
    await log_employee_activity(
        auth=auth,
        entity_type="attendance",
        entity_id=existing["id"],
        action=f"clocked out ({hours} hrs)",
        details=f"Ended work session. Duration: {duration_mins} mins",
    )

    return AttendanceLog(**res)


@router.get("/attendance/status", response_model=AttendanceStatusOut)
async def get_attendance_status(auth: AuthContext = Depends(require_employee)):
    """
    Get current clock-in state, active session (if any), and total minutes worked today.
    """
    active_session = await db.attendance_logs.find_one(
        {"employee_id": auth.employee_id, "clock_out_time": None},
        {"_id": 0},
    )

    today_str = _now_utc().strftime("%Y-%m-%d")

    # Sum completed sessions for today
    today_cursor = db.attendance_logs.find(
        {"employee_id": auth.employee_id, "date": today_str},
        {"_id": 0, "duration_minutes": 1, "clock_in_time": 1, "clock_out_time": 1},
    )

    total_mins = 0.0
    async for s in today_cursor:
        if s.get("duration_minutes") is not None:
            total_mins += float(s["duration_minutes"])
        elif s.get("clock_out_time") is None:
            # Active session — compute elapsed
            try:
                in_time = date_parser.isoparse(s["clock_in_time"])
                if in_time.tzinfo is None:
                    in_time = in_time.replace(tzinfo=timezone.utc)
                elapsed = max(0.0, (_now_utc() - in_time).total_seconds() / 60.0)
                total_mins += elapsed
            except Exception:
                pass

    return AttendanceStatusOut(
        is_clocked_in=bool(active_session),
        current_session=AttendanceLog(**active_session) if active_session else None,
        today_total_minutes=round(total_mins, 2),
    )


@router.get("/attendance/history", response_model=List[AttendanceLog])
async def get_attendance_history(
    employee_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    auth: AuthContext = Depends(require_auth),
):
    """
    List attendance history.
    Employees can only see their own history. Owner can see any employee's history.
    """
    target_emp_id = auth.employee_id
    if auth.is_owner:
        target_emp_id = employee_id

    query = {}
    if target_emp_id:
        query["employee_id"] = target_emp_id

    cursor = db.attendance_logs.find(query, {"_id": 0}).sort("clock_in_time", -1).limit(limit)
    return [AttendanceLog(**d) async for d in cursor]
