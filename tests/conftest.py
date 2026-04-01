"""Shared pytest fixtures for the Jira Emulator test suite.

Each test function gets a fresh in-memory SQLite database with seed data
loaded via the application lifespan.  The async HTTP client talks directly
to the ASGI app -- no real network socket is opened.
"""

import os
from collections.abc import AsyncIterator

import pytest
import httpx

# ---------------------------------------------------------------------------
# Environment variables MUST be set before any application code is imported
# so that pydantic-settings picks them up from the environment.
# ---------------------------------------------------------------------------
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["AUTH_MODE"] = "permissive"
os.environ["SEED_DATA"] = "true"

# Base64-encoded "admin:admin"
AUTH_HEADER = {"Authorization": "Basic YWRtaW46YWRtaW4="}


@pytest.fixture()
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Yield an httpx.AsyncClient wired to a fresh FastAPI app instance.

    * Clears the cached pydantic Settings so env-var overrides apply.
    * Resets the global SQLAlchemy engine so every test gets its own
      in-memory database.
    * Enters the app lifespan context so that tables are created and
      seed data is loaded before the first request.
    """
    # Clear the cached settings so env-var changes are picked up
    from jira_emulator.config import get_settings
    get_settings.cache_clear()

    # Reset the global engine / session factory so the new in-memory DB
    # is used for this test.
    from jira_emulator.database import reset_engine
    reset_engine()

    # Build a brand-new FastAPI application
    from jira_emulator.app import create_app, lifespan
    app = create_app()

    # Enter the lifespan so tables + seed data are ready, then yield the
    # async HTTP client.
    async with lifespan(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac
