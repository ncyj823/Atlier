"""
app/main.py — FastAPI application factory.

Wires together:
  - Application lifespan (DB connect/disconnect, scheduler start/stop)
  - CORS middleware
  - Public routes (health, employee login, public share page)
  - Authenticated routes (Owner + Employee RBAC)
  - Owner-only admin & financial routes
  - Startup reminder reconciliation

Start with:
  uvicorn app.main:app --host 0.0.0.0 --port 8000 [--reload]
"""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import require_api_key, require_owner
from app.config import settings
from app.database import close_db, connect_db
from app.routes import (
    admin_employees,
    attendance,
    clients,
    employee_auth,
    events,
    health,
    invoices,
    pdfs,
    projects,
    reports,
    salary,
    seed,
    share,
    tasks,
    transcribe,
)
from app.services.scheduler import reconcile_reminders_on_startup, scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Startup:  connect to MongoDB, start APScheduler, reconcile pending reminders.
    Shutdown: stop scheduler, close MongoDB connection.
    """
    # ── Startup ────────────────────────────────────────────────────────────────
    await connect_db()

    try:
        scheduler.start()
        logger.info("APScheduler started")
    except Exception as exc:
        logger.error("APScheduler start failed: %s", exc)

    # Re-derive reminder jobs for all upcoming events so a restart/deploy
    # doesn't silently drop pending reminder emails.
    from app.database import get_db
    await reconcile_reminders_on_startup(get_db())

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    try:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
    except Exception:
        pass

    await close_db()


# ── Application factory ────────────────────────────────────────────────────────

app = FastAPI(
    title="Atelier API",
    description="Fashion freelancer management — clients, projects, invoices, calendar, employee tracking.",
    version="2.1.0",
    lifespan=lifespan,
)


# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://atlier.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Public (unauthenticated) routes ────────────────────────────────────────────
app.include_router(health.router)
app.include_router(share.public_router, prefix="/api")
app.include_router(employee_auth.router, prefix="/api")

# Root endpoint (preserves existing GET /api/ → {app, ok})
from fastapi import APIRouter as _APIRouter
_root = _APIRouter(prefix="/api")

@_root.get("/")
async def root():
    return {"app": "Atelier", "ok": True}

app.include_router(_root)


# ── Authenticated Multi-Tier routes (Owner X-API-Key or Employee JWT) ──────────
# These routes perform internal RBAC checks to enforce assigned client permissions.
app.include_router(clients.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(pdfs.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(attendance.router, prefix="/api")
app.include_router(transcribe.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")


# ── Strictly Owner-Only routes (Invoices, Admin, Reports, Share Gen, Seed) ─────
_owner_dep = [Depends(require_owner)]

app.include_router(invoices.router, prefix="/api", dependencies=_owner_dep)
app.include_router(admin_employees.router, prefix="/api", dependencies=_owner_dep)
app.include_router(reports.router, prefix="/api", dependencies=_owner_dep)
app.include_router(salary.router, prefix="/api", dependencies=_owner_dep)
app.include_router(share.auth_router, prefix="/api", dependencies=_owner_dep)
app.include_router(seed.router, prefix="/api", dependencies=_owner_dep)
