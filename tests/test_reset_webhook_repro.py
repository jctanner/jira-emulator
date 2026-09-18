import httpx
import pytest


@pytest.mark.asyncio
async def test_reset_file_database_with_webhook_worker(tmp_path, monkeypatch):
    db_path = tmp_path / "jira.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("AUTH_MODE", "permissive")
    monkeypatch.setenv("SEED_DATA", "true")
    monkeypatch.setenv("WEBHOOKS_ENABLED", "true")
    monkeypatch.setenv("WEBHOOK_WORKER_POLL_SECONDS", "0.01")

    from jira_emulator.config import get_settings
    from jira_emulator.database import reset_engine

    get_settings.cache_clear()
    reset_engine()

    from jira_emulator.app import create_app, lifespan

    app = create_app()
    async with (
        lifespan(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client,
    ):
        for _ in range(20):
            response = await client.post(
                "/api/admin/reset",
                headers={"Authorization": "Basic YWRtaW46YWRtaW4="},
            )
            assert response.status_code == 200, response.text
