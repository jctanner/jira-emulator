"""FastAPI application factory."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from jira_emulator import __version__
from jira_emulator.config import get_settings
from jira_emulator.database import get_database_lock, get_session_factory, init_db
from jira_emulator.exceptions import (
    DescriptionContentLimitExceededError,
    InvalidTransitionError,
    IssueNotFoundError,
    JQLParseError,
    ProjectNotFoundError,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    settings = get_settings()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Import models so Base.metadata knows all tables
    import jira_emulator.models  # noqa: F401

    # Create tables
    await init_db()
    logger.info("Database tables created")

    # Seed data
    if settings.SEED_DATA:
        from jira_emulator.services.seed_service import load_seed_data

        factory = get_session_factory()
        async with factory() as db:
            try:
                await load_seed_data(db, settings.ADMIN_PASSWORD)
            except Exception:
                logger.exception("Failed to load seed data")

    from jira_emulator.services.seed_service import DEFAULT_API_TOKEN

    logger.info("Auth mode: %s", settings.AUTH_MODE)
    logger.info("Default credentials: %s / %s", settings.DEFAULT_USER, settings.ADMIN_PASSWORD)
    logger.info("Default API token: %s", DEFAULT_API_TOKEN)
    logger.info("Web UI: %s", settings.BASE_URL)

    # Import on startup
    if settings.IMPORT_ON_STARTUP:
        import os

        import_dir = settings.IMPORT_DIR
        if os.path.isdir(import_dir):
            from jira_emulator.services.import_service import import_directory

            factory = get_session_factory()
            async with factory() as db:
                try:
                    result = await import_directory(db, import_dir)
                    await db.commit()
                    logger.info(
                        f"Startup import: {result.imported} imported, "
                        f"{result.updated} updated, {len(result.errors)} errors"
                    )
                except Exception:
                    logger.exception("Failed startup import")
        else:
            logger.warning(f"IMPORT_DIR '{import_dir}' does not exist, skipping startup import")

    worker_task = None
    database_lock = get_database_lock()
    app.state.database_operation_lock = database_lock
    # In-memory SQLite uses one shared connection; a background session would
    # contend with request sessions and make tests/non-server embeds unsafe.
    if settings.WEBHOOKS_ENABLED and settings.DATABASE_URL != "sqlite+aiosqlite://":
        from datetime import datetime, timedelta

        from jira_emulator.models.webhook import WebhookOutbox
        from jira_emulator.services.webhook_service import claim_due, deliver_once

        async def worker():
            while True:
                async with database_lock:
                    factory = get_session_factory()
                    async with factory() as db:
                        stale = (
                            (
                                await db.execute(
                                    __import__("sqlalchemy")
                                    .select(WebhookOutbox)
                                    .where(WebhookOutbox.state == "delivering")
                                )
                            )
                            .scalars()
                            .all()
                        )
                        for row in stale:
                            row.state = "pending"
                            row.next_attempt_at = datetime.utcnow()
                        await db.commit()
                        rows = await claim_due(db)
                    for row in rows:
                        ok, status, error = await deliver_once(row)
                        async with factory() as db:
                            fresh = await db.get(WebhookOutbox, row.id)
                            if fresh is None:
                                continue
                            fresh.last_status = status
                            fresh.last_error = error
                            if ok:
                                fresh.state = "delivered"
                                fresh.delivered_at = datetime.utcnow()
                            elif fresh.attempt_count >= 6 or (
                                status is not None and status < 500 and status not in {408, 409, 425, 429}
                            ):
                                fresh.state = "failed"
                                fresh.failed_at = datetime.utcnow()
                            else:
                                fresh.state = "pending"
                                fresh.next_attempt_at = datetime.utcnow() + timedelta(
                                    seconds=min(900, 2**fresh.attempt_count)
                                )
                            await db.commit()
                await asyncio.sleep(settings.WEBHOOK_WORKER_POLL_SECONDS)

        worker_task = asyncio.create_task(worker())
    try:
        yield
    finally:
        if worker_task:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Jira Emulator",
        description="A lightweight Jira REST API v2 emulator",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rewrite /rest/api/3/ -> /rest/api/2/ so v3 clients work
    class ApiVersionRewriteMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if request.url.path.startswith("/rest/api/3/"):
                request.state.api_version = 3
                new_path = "/rest/api/2/" + request.url.path[len("/rest/api/3/") :]
                request.scope["path"] = new_path
            else:
                request.state.api_version = 2
            return await call_next(request)

    app.add_middleware(ApiVersionRewriteMiddleware)

    class DatabaseOperationMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if request.url.path == "/api/admin/reset":
                return await call_next(request)
            async with app.state.database_operation_lock:
                return await call_next(request)

    app.add_middleware(DatabaseOperationMiddleware)

    # Request logging
    class RequestLoggingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            start = time.perf_counter()
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "%s %s %d %.1fms",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            return response

    app.add_middleware(RequestLoggingMiddleware)

    # Register routers
    from jira_emulator.routers import (
        admin,
        attachments,
        auth,
        fields,
        issue_properties,
        issues,
        links,
        metadata,
        projects,
        remote_links,
        search,
        tokens,
        users,
        webhooks,
    )

    app.include_router(auth.router)
    app.include_router(attachments.router)
    app.include_router(issues.router)
    app.include_router(search.router)
    app.include_router(projects.router)
    app.include_router(metadata.router)
    app.include_router(fields.router)
    app.include_router(users.router)
    app.include_router(tokens.router)
    app.include_router(links.router)
    app.include_router(remote_links.router)
    app.include_router(issue_properties.router)
    app.include_router(admin.router)
    app.include_router(webhooks.api_router)
    app.include_router(webhooks.admin_router)

    # Web UI router
    from jira_emulator.web.routes import router as web_router

    app.include_router(web_router)

    # Global exception handler for Jira-format errors
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content={"errorMessages": [str(exc)], "errors": {}},
        )

    @app.exception_handler(DescriptionContentLimitExceededError)
    async def description_content_limit_handler(request: Request, exc: DescriptionContentLimitExceededError):
        return JSONResponse(
            status_code=400,
            content={"errorMessages": [], "errors": {exc.field: exc.code}},
        )

    @app.exception_handler(IssueNotFoundError)
    async def issue_not_found_handler(request: Request, exc: IssueNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"errorMessages": [str(exc)], "errors": {}},
        )

    @app.exception_handler(ProjectNotFoundError)
    async def project_not_found_handler(request: Request, exc: ProjectNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"errorMessages": [str(exc)], "errors": {}},
        )

    @app.exception_handler(InvalidTransitionError)
    async def invalid_transition_handler(request: Request, exc: InvalidTransitionError):
        return JSONResponse(
            status_code=400,
            content={"errorMessages": [str(exc)], "errors": {}},
        )

    @app.exception_handler(JQLParseError)
    async def jql_parse_error_handler(request: Request, exc: JQLParseError):
        return JSONResponse(
            status_code=400,
            content={"errorMessages": [str(exc)], "errors": {}},
        )

    return app
