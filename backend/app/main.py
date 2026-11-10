"""EduCrew API. Run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 (from backend/)."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db as db_module
from app.config import get_settings
from app.models import User
from app.routers import adjustments, admin, analytics, auth, campus_map, logs, tickets, timetable
from app.services.adjustments import AdjustmentError
from app.services.events import broker
from app.services.logs import LogError
from app.services.settings_store import seed_defaults
from app.services.tickets import TicketError, run_deadline_checks

log = logging.getLogger("educrew")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _deadline_job() -> None:
    session = db_module.SessionLocal()
    try:
        result = run_deadline_checks(session)
        if result["escalated"] or result["reminded"]:
            log.info("Deadline check: escalated %s, reminded %s", result["escalated"], result["reminded"])
    except Exception:  # noqa: BLE001 — never let the scheduler thread die
        log.exception("Deadline check failed")
        session.rollback()
    finally:
        session.close()


def _prepare_database(auto_seed: bool) -> None:
    db_module.create_all()
    session = db_module.SessionLocal()
    try:
        seed_defaults(session)
        session.commit()
        empty = session.query(User).first() is None
    finally:
        session.close()
    if empty and auto_seed:
        from app.seed import run_seed

        log.info("Empty database: loading demo data (python -m app.seed resets it any time)")
        run_seed()


def create_app(auto_seed: bool = True) -> FastAPI:
    settings = get_settings()
    if db_module.engine is None:
        db_module.init_engine(settings.database_url)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        broker.bind_loop(asyncio.get_running_loop())
        _prepare_database(auto_seed)
        scheduler = None
        if settings.scheduler_enabled:
            scheduler = BackgroundScheduler()
            scheduler.add_job(_deadline_job, "interval", seconds=settings.scheduler_interval_seconds,
                              max_instances=1, coalesce=True, id="deadlines")
            scheduler.start()
        log.info("EduCrew API ready. Gemini: %s. SMTP: %s. Demo mode: %s.",
                 "on" if settings.gemini_api_key else "off (rule-based triage)",
                 "on" if settings.smtp_configured else "off (emails go to the outbox)",
                 settings.demo_mode)
        yield
        if scheduler:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="EduCrew API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    for error_type in (TicketError, AdjustmentError, LogError):
        @app.exception_handler(error_type)
        async def _service_error(_request: Request, exc):  # noqa: ANN001
            return JSONResponse(status_code=exc.status, content={"detail": exc.message})

    for router in (auth.router, tickets.router, campus_map.router, adjustments.router, timetable.router,
                   logs.router, analytics.router, admin.router):
        app.include_router(router)
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
    return app


app = create_app()
