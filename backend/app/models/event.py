"""
app/models/event.py — Calendar event Pydantic schemas.
"""
from pydantic import BaseModel, field_validator
from typing import List, Literal, Optional
from app.models.common import validate_email_field

EVENT_MODES = ["design_call", "measurement_call", "sending_pieces", "personal"]


class EventCreate(BaseModel):
    title: str
    mode: Literal["design_call", "measurement_call", "sending_pieces", "personal"]
    start_iso: str  # ISO 8601 with timezone offset
    duration_minutes: int = 30
    client_id: Optional[str] = None
    client_email: Optional[str] = ""
    notes: Optional[str] = ""

    @field_validator("client_email")
    @classmethod
    def _check_email(cls, v):
        return validate_email_field(v)


class EventOut(BaseModel):
    id: str
    title: str
    mode: str
    start_iso: str
    duration_minutes: int
    client_id: Optional[str] = None
    client_name: Optional[str] = ""
    client_email: Optional[str] = ""
    notes: str = ""
    meet_link: str
    reminders: List[str] = []
    created_at: str


class EventReschedule(BaseModel):
    start_iso: str
