from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    status: Literal["pending", "in_progress", "completed"] = "pending"


class TaskCreate(TaskBase):
    assigned_employee_id: str


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Literal["pending", "in_progress", "completed"]] = None
    assigned_employee_id: Optional[str] = None


class TaskOut(TaskBase):
    id: str
    project_id: str
    assigned_employee_id: str
    created_at: str
    completed_at: Optional[str] = None
    created_by: str
