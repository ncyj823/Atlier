"""
app/models/employee.py — Employee account Pydantic schemas.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class EmployeeCreate(BaseModel):
    name: str = Field(..., min_length=1)
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=4)
    assigned_client_ids: List[str] = Field(default_factory=list)
    active: bool = True


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    assigned_client_ids: Optional[List[str]] = None
    active: Optional[bool] = None


class EmployeeOut(BaseModel):
    id: str
    name: str
    username: str
    assigned_client_ids: List[str] = Field(default_factory=list)
    active: bool = True
    created_at: str
    updated_at: Optional[str] = None


class EmployeeLogin(BaseModel):
    username: str
    password: str


class EmployeeLoginOut(BaseModel):
    token: str
    token_type: str = "bearer"
    employee: EmployeeOut
