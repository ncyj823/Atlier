"""
app/services/activity_logger.py — Automated Activity Logger.

Automatically logs actions performed by employees (opening/viewing/editing clients & projects)
for auditing, activity feeds, and owner monthly reports.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.auth import AuthContext
from app.database import db

logger = logging.getLogger(__name__)


async def log_employee_activity(
    auth: Optional[AuthContext],
    entity_type: str,
    entity_id: str,
    action: str,
    client_id: Optional[str] = None,
    project_id: Optional[str] = None,
    details: Optional[str] = "",
) -> None:
    """
    Log an activity entry if the authenticated caller is an employee.
    Fails safely — errors are logged and never bubble up to break the request.
    """
    if not auth or not auth.is_employee or not auth.employee_id:
        return

    try:
        now = datetime.now(timezone.utc)
        doc = {
            "id": str(uuid.uuid4()),
            "employee_id": auth.employee_id,
            "employee_name": auth.name or auth.username or "",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "client_id": client_id,
            "project_id": project_id,
            "action": action,
            "details": details or "",
            "timestamp": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
        }
        await db.activity_logs.insert_one(doc)
    except Exception as exc:
        logger.warning("Failed to record employee activity log: %s", exc)
