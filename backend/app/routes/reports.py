"""
app/routes/reports.py — Owner-only Monthly Time & Activity Reports.

Endpoints:
  GET /api/admin/reports/monthly — Aggregated hours and day-by-day activity timelines
"""
import calendar
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.auth import AuthContext, require_owner
from app.database import db
from app.models.activity import ActivityLog
from app.models.attendance import AttendanceLog
from app.models.report import DayActivitySummary, EmployeeMonthlyReport, MonthlyReportResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["reports"])


def _default_month_str() -> str:
    """
    Default to current month (YYYY-MM).
    """
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m")


@router.get("/admin/reports/monthly", response_model=MonthlyReportResponse)
async def get_monthly_report(
    month: Optional[str] = Query(
        default=None,
        description="Target month in YYYY-MM format (e.g. 2026-08)",
        regex=r"^\d{4}-\d{2}$",
    ),
    employee_id: Optional[str] = Query(
        default=None,
        description="Filter report to a specific employee ID",
    ),
    auth: AuthContext = Depends(require_owner),
):
    """
    Owner-only monthly report:
      - Computes total hours worked per employee for the specified month.
      - Provides a day-by-day list of what they worked on (from ActivityLog)
        and their clock-in/out attendance sessions.
    """
    target_month = month or _default_month_str()

    # Build employee query
    emp_query = {}
    if employee_id:
        emp_query["id"] = employee_id

    cursor = db.employees.find(emp_query, {"_id": 0, "hashed_password": 0}).sort("name", 1)
    employees = [d async for d in cursor]

    employee_reports: List[EmployeeMonthlyReport] = []
    grand_total_hours = 0.0

    for emp in employees:
        emp_id = emp["id"]

        # Fetch attendance logs for this employee in the target month
        att_cursor = db.attendance_logs.find(
            {
                "employee_id": emp_id,
                "date": {"$regex": f"^{target_month}-"},
            },
            {"_id": 0},
        ).sort("clock_in_time", 1)
        att_logs = [AttendanceLog(**d) async for d in att_cursor]

        # Fetch activity logs for this employee in the target month
        act_cursor = db.activity_logs.find(
            {
                "employee_id": emp_id,
                "date": {"$regex": f"^{target_month}-"},
            },
            {"_id": 0},
        ).sort("timestamp", 1)
        act_logs = [ActivityLog(**d) async for d in act_cursor]

        # Group by day
        days_sessions = defaultdict(list)
        days_activities = defaultdict(list)

        for att in att_logs:
            days_sessions[att.date].append(att)

        for act in act_logs:
            days_activities[act.date].append(act)

        all_dates = sorted(set(list(days_sessions.keys()) + list(days_activities.keys())), reverse=True)

        daily_breakdowns: List[DayActivitySummary] = []
        emp_total_minutes = 0.0

        for d in all_dates:
            sessions = days_sessions.get(d, [])
            activities = days_activities.get(d, [])

            day_minutes = 0.0
            for s in sessions:
                if s.duration_minutes is not None:
                    day_minutes += s.duration_minutes

            emp_total_minutes += day_minutes

            daily_breakdowns.append(
                DayActivitySummary(
                    date=d,
                    total_minutes=round(day_minutes, 2),
                    total_hours=round(day_minutes / 60.0, 2),
                    sessions=sessions,
                    activities=activities,
                )
            )

        emp_total_hours = round(emp_total_minutes / 60.0, 2)
        grand_total_hours += emp_total_hours

        employee_reports.append(
            EmployeeMonthlyReport(
                employee_id=emp_id,
                employee_name=emp.get("name", "Unknown"),
                username=emp.get("username", ""),
                month=target_month,
                total_minutes=round(emp_total_minutes, 2),
                total_hours=emp_total_hours,
                days_worked=len([day for day in daily_breakdowns if day.total_minutes > 0 or day.sessions]),
                total_activities=len(act_logs),
                daily_breakdown=daily_breakdowns,
            )
        )

    return MonthlyReportResponse(
        month=target_month,
        employees=employee_reports,
        total_team_hours=round(grand_total_hours, 2),
    )
