"""
app/models/invoice.py — Invoice Pydantic schemas.
"""
import uuid
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime, timezone


class InvoiceItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    amount: float
    status: Literal["pending", "cleared"] = "pending"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class InvoiceItemCreate(BaseModel):
    description: str
    amount: float
    status: Literal["pending", "cleared"] = "pending"
