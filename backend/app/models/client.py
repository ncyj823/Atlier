"""
app/models/client.py — Client Pydantic schemas.
"""
from pydantic import BaseModel, field_validator
from typing import Optional
from app.models.common import validate_email_field


class ClientCreate(BaseModel):
    name: str
    whatsapp: Optional[str] = ""
    email: Optional[str] = ""
    measurements: Optional[dict] = {}
    notes: Optional[str] = ""

    @field_validator("email")
    @classmethod
    def _check_email(cls, v):
        return validate_email_field(v)


class ClientUpdate(BaseModel):
    """
    Separate from ClientCreate on purpose: every field defaults to None so
    a PUT that omits a field leaves it untouched instead of blanking it out.
    """
    name: Optional[str] = None
    whatsapp: Optional[str] = None
    email: Optional[str] = None
    measurements: Optional[dict] = None
    notes: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _check_email(cls, v):
        return validate_email_field(v)


class ClientOut(BaseModel):
    id: str
    name: str
    whatsapp: str = ""
    email: str = ""
    measurements: dict = {}
    notes: str = ""
    created_at: str
    avatar_url: Optional[str] = None
