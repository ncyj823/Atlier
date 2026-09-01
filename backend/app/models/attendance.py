"""
app/models/attendance.py — Attendance and clock-in/out Pydantic schemas.
"""
from typing import Optional
from pydantic import BaseModel


class AttendanceLog(BaseModel):
    id: str
    employee_id: str
    employee_name: str = ""
    clock_in_time: str
    clock_out_time: Optional[str] = None
    date: str  # YYYY-MM-DD
    duration_minutes: Optional[float] = None
    created_at: str


class AttendanceStatusOut(BaseModel):
    is_clocked_in: bool
    current_session: Optional[AttendanceLog] = None
    today_total_minutes: float = 0.0
