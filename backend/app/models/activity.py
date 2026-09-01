"""
app/models/activity.py — Employee Activity Log Pydantic schemas.
"""
from typing import Optional
from pydantic import BaseModel


class ActivityLog(BaseModel):
    id: str
    employee_id: str
    employee_name: str = ""
    entity_type: str  # "client", "project", "canvas", "pdf"
    entity_id: str
    client_id: Optional[str] = None
    project_id: Optional[str] = None
    action: str  # e.g., "viewed client measurements", "updated project"
    details: Optional[str] = ""
    timestamp: str  # ISO 8601 timestamp
    date: str  # YYYY-MM-DD
