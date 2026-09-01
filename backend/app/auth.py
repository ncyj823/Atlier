"""
app/auth.py — Unified Authentication & Role-Based Access Control.

Supports:
  1. Owner tier: Authenticated via X-API-Key header (preserved exactly from v1).
  2. Employee tier: Authenticated via JWT Bearer token (Authorization: Bearer <token>)
     or X-Employee-Token header.

Provides:
  - AuthContext: Dataclass containing role ("owner" | "employee") and employee details.
  - require_api_key: Legacy/strict owner dependency (preserves exact behavior).
  - get_current_auth: Accepts either Owner X-API-Key or Employee JWT token.
  - require_owner: Enforces owner role (raises 403 for employees).
  - require_employee: Enforces employee role (raises 403 for owners).
  - require_auth: Accepts either valid Owner or active Employee.
  - Password hashing (bcrypt) and JWT encode/decode helpers.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)


# ── Password Hashing ─────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt salt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception as exc:
        logger.warning("Password verification failed with error: %s", exc)
        return False


# ── JWT Session Tokens ───────────────────────────────────────────────────────

def _get_jwt_secret() -> str:
    return settings.jwt_secret or settings.api_key or "atelier-secret-key-fallback"


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.jwt_expiration_days)
    to_encode.update({"iat": now, "exp": expire})
    return jwt.encode(to_encode, _get_jwt_secret(), algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and validate a signed JWT token. Raises HTTPException on error."""
    try:
        payload = jwt.decode(
            token,
            _get_jwt_secret(),
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token has expired. Please log in again.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token.",
        )


# ── AuthContext ──────────────────────────────────────────────────────────────

class AuthContext(BaseModel):
    role: Literal["owner", "employee"]
    employee_id: Optional[str] = None
    username: Optional[str] = None
    name: Optional[str] = None
    assigned_client_ids: List[str] = Field(default_factory=list)

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    @property
    def is_employee(self) -> bool:
        return self.role == "employee"

    def can_access_client(self, client_id: Optional[str]) -> bool:
        """Return True if owner or if client_id is in employee's assigned_client_ids."""
        if self.is_owner:
            return True
        if not client_id:
            return False
        return client_id in self.assigned_client_ids


# ── Dependencies ─────────────────────────────────────────────────────────────

async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """
    Legacy owner dependency: validates X-API-Key against settings.api_key.
    Preserved for full backward compatibility with original route dependencies.
    """
    if not settings.api_key:
        logger.critical(
            "SERVER MISCONFIGURED: API_KEY environment variable is not set. "
            "Set API_KEY in your .env file and restart."
        )
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: API_KEY is not set",
        )

    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


async def get_current_auth(
    x_api_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    x_employee_token: Optional[str] = Header(default=None),
) -> AuthContext:
    """
    Universal auth dependency:
      - If valid X-API-Key is provided -> returns AuthContext(role="owner")
      - If Bearer token or X-Employee-Token is provided -> validates JWT and
        loads active employee record from DB, returning AuthContext(role="employee", ...)
      - Otherwise -> raises 401 Unauthorized
    """
    # 1. Check Owner API Key
    if x_api_key and settings.api_key and secrets.compare_digest(x_api_key, settings.api_key):
        return AuthContext(role="owner")

    # 2. Check Employee Token
    token: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_employee_token:
        token = x_employee_token.strip()

    if token:
        payload = decode_access_token(token)
        emp_id = payload.get("sub") or payload.get("employee_id")
        if not emp_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        # Verify employee in DB (lazy import to prevent circular dependency)
        from app.database import db

        emp = await db.employees.find_one({"id": emp_id}, {"_id": 0})
        if not emp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Employee account not found",
            )
        if not emp.get("active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Employee account is deactivated. Contact the owner.",
            )

        return AuthContext(
            role="employee",
            employee_id=emp["id"],
            username=emp["username"],
            name=emp["name"],
            assigned_client_ids=emp.get("assigned_client_ids", []),
        )

    # 3. No valid credentials provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication credentials",
    )


async def require_owner(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
    """Dependency that strictly requires Owner role."""
    if not auth.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Owner access required",
        )
    return auth


async def require_employee(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
    """Dependency that strictly requires Employee role."""
    if not auth.is_employee:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Employee access required",
        )
    return auth


async def require_auth(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
    """Dependency that accepts either valid Owner or active Employee."""
    return auth
