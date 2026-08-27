"""
app/models/common.py — Shared model helpers used across multiple modules.
"""
import re
from pydantic import BaseModel


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validate_email_field(v: str | None) -> str | None:
    """
    Validate an optional email field.
    - None / "" are allowed (fields are optional throughout the app).
    - Rejects header-injection characters (\n \r) and malformed addresses.
    """
    if v is None or v == "":
        return v
    v = v.strip()
    if "\n" in v or "\r" in v or not _EMAIL_RE.match(v):
        raise ValueError(f"invalid email address: {v!r}")
    return v


class PDFUpload(BaseModel):
    name: str
    data_base64: str  # raw base64-encoded file content


class ParseRequest(BaseModel):
    text: str
    default_tz: str = "Asia/Kolkata"
