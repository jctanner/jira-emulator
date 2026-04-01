"""FastAPI application factory."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from jira_emulator import __version__
from jira_emulator.config import get_settings
from jira_emulator.database import get_session_factory, init_db
from jira_emulator.exceptions import (
    IssueNotFoundError,
    ProjectNotFoundError,
    InvalidTransitionError,
    JQLParseError,
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

    yield


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
                new_path = "/rest/api/2/" + request.url.path[len("/rest/api/3/"):]
                request.scope["path"] = new_path
            return await call_next(request)

    app.add_middleware(ApiVersionRewriteMiddleware)

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
        auth,
        fields,
        issues,
        links,
        metadata,
        projects,
        search,
        tokens,
        users,
    )

    app.include_router(auth.router)
    app.include_router(issues.router)
    app.include_router(search.router)
    app.include_router(projects.router)
    app.include_router(metadata.router)
    app.include_router(fields.router)
    app.include_router(users.router)
    app.include_router(tokens.router)
    app.include_router(links.router)
    app.include_router(admin.router)

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
