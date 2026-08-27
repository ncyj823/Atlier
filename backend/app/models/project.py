"""
app/models/project.py — Project and Canvas Pydantic schemas.
"""
from pydantic import BaseModel
from typing import List, Literal, Optional


class ProjectCreate(BaseModel):
    client_id: str
    title: str
    delivery_location: Optional[str] = ""
    deadline: Optional[str] = None  # ISO date string e.g. "2026-08-15"
    description: Optional[str] = ""
    total_amount: Optional[float] = 0.0
    paid_amount: Optional[float] = 0.0
    status: Optional[Literal["ongoing", "completed"]] = "ongoing"
    mannequin_gender: Optional[Literal["female", "male"]] = "female"


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    delivery_location: Optional[str] = None
    deadline: Optional[str] = None
    description: Optional[str] = None
    total_amount: Optional[float] = None
    paid_amount: Optional[float] = None
    status: Optional[Literal["ongoing", "completed"]] = None


class CanvasSave(BaseModel):
    gender: Literal["female", "male"]
    strokes: List[dict]  # [{ d: "M0 0 L10 10", color: "#000", width: 3 }, ...]
