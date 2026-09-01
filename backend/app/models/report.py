"""
app/models/report.py — Owner Monthly Time & Activity Report Pydantic schemas.
"""
from typing import List
from pydantic import BaseModel
from app.models.attendance import AttendanceLog
from app.models.activity import ActivityLog


class DayActivitySummary(BaseModel):
    date: str  # YYYY-MM-DD
    total_minutes: float = 0.0
    total_hours: float = 0.0
    sessions: List[AttendanceLog] = []
    activities: List[ActivityLog] = []


class EmployeeMonthlyReport(BaseModel):
    employee_id: str
    employee_name: str
    username: str
    month: str  # YYYY-MM
    total_minutes: float = 0.0
    total_hours: float = 0.0
    days_worked: int = 0
    total_activities: int = 0
    daily_breakdown: List[DayActivitySummary] = []


class MonthlyReportResponse(BaseModel):
    month: str
    employees: List[EmployeeMonthlyReport] = []
    total_team_hours: float = 0.0
