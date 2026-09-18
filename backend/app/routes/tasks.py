import logging
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import AuthContext, get_current_auth, require_owner
from app.database import db
from app.models.task import TaskCreate, TaskOut, TaskUpdate
from app.services.activity_logger import log_employee_activity

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tasks"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/projects/{project_id}/tasks", response_model=TaskOut)
async def create_task(
    project_id: str,
    payload: TaskCreate,
    auth: AuthContext = Depends(require_owner),
):
    """
    Create a new task. Owner only.
    Assigns a task to a specific employee for a specific project.
    """
    # Verify project exists
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Verify assigned employee exists
    emp = await db.employees.find_one({"id": payload.assigned_employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assigned employee not found",
        )

    doc = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "assigned_employee_id": payload.assigned_employee_id,
        "title": payload.title.strip(),
        "description": payload.description.strip() if payload.description else "",
        "status": payload.status,
        "created_at": _now_iso(),
        "completed_at": _now_iso() if payload.status == "completed" else None,
        "created_by": auth.employee_id or "owner",
    }

    await db.tasks.insert_one(doc)
    doc.pop("_id", None)
    return TaskOut(**doc)


@router.get("/projects/{project_id}/tasks", response_model=List[TaskOut])
async def list_tasks(
    project_id: str,
    auth: AuthContext = Depends(get_current_auth),
):
    """
    List tasks for a project.
    Owner sees all tasks.
    Employee sees only their tasks, provided they have access to the project's client.
    """
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if auth.is_employee:
        if not auth.can_access_client(project.get("client_id")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Not assigned to this project's client",
            )
        
        cursor = db.tasks.find({
            "project_id": project_id,
            "assigned_employee_id": auth.employee_id
        }, {"_id": 0}).sort("created_at", -1)
    else:
        cursor = db.tasks.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1)

    return [TaskOut(**d) async for d in cursor]


@router.put("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Update a task.
    Owner can update any field.
    Employee can only update the status of their own tasks, and only if they have access to the project's client.
    Automatically logs status changes.
    """
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    project_id = task["project_id"]
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if auth.is_employee:
        if task["assigned_employee_id"] != auth.employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Task is not assigned to you",
            )
        if not auth.can_access_client(project.get("client_id")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Not assigned to this project's client",
            )
        
        # Employees can only update status
        update_data = {}
        if payload.status is not None:
            update_data["status"] = payload.status
            if payload.status == "completed" and task["status"] != "completed":
                update_data["completed_at"] = _now_iso()
            elif payload.status != "completed":
                update_data["completed_at"] = None

        if not update_data:
             return TaskOut(**task) # nothing to update
    else:
        # Owner can update anything
        update_data = payload.dict(exclude_unset=True)
        if "status" in update_data:
             if update_data["status"] == "completed" and task["status"] != "completed":
                 update_data["completed_at"] = _now_iso()
             elif update_data["status"] != "completed":
                 update_data["completed_at"] = None

    await db.tasks.update_one({"id": task_id}, {"$set": update_data})
    updated_task = await db.tasks.find_one({"id": task_id}, {"_id": 0})

    # Log activity if status changed
    if "status" in update_data and update_data["status"] != task["status"]:
        await log_employee_activity(
            auth=auth,
            action="update",
            entity_type="task",
            entity_id=task_id,
            details=f"Task '{updated_task['title']}' status changed to {update_data['status']}"
        )

    return TaskOut(**updated_task)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    auth: AuthContext = Depends(require_owner),
):
    """
    Delete a task. Owner only.
    """
    result = await db.tasks.delete_one({"id": task_id})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
