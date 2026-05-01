"""Fixtures for integration tests against a live server stack."""

import base64
import os

import httpx
import pytest

API_PORT = int(os.environ.get("INTEGRATION_API_PORT", "9876"))
MCP_PORT = int(os.environ.get("INTEGRATION_MCP_PORT", "9877"))

API_BASE_URL = f"http://localhost:{API_PORT}"
MCP_SSE_URL = f"http://localhost:{MCP_PORT}/sse"

_creds = base64.b64encode(b"admin:admin").decode()
AUTH_HEADER = {"Authorization": f"Basic {_creds}"}


def pytest_collection_modifyitems(config, items):
    if not os.environ.get("INTEGRATION_API_PORT"):
        skip = pytest.mark.skip(reason="Integration server not running (no INTEGRATION_API_PORT)")
        for item in items:
            if "integration" in str(item.fspath):
                item.add_marker(skip)


@pytest.fixture(scope="session")
def api_base_url() -> str:
    return API_BASE_URL


@pytest.fixture(scope="session")
def mcp_sse_url() -> str:
    return MCP_SSE_URL


@pytest.fixture(scope="session")
def auth_header() -> dict[str, str]:
    return AUTH_HEADER


@pytest.fixture()
async def client(api_base_url: str, auth_header: dict) -> httpx.AsyncClient:
    async with httpx.AsyncClient(base_url=api_base_url) as ac:
        resp = await ac.post("/api/admin/reset", headers=auth_header)
        assert resp.status_code == 200, f"DB reset failed: {resp.text}"
        yield ac
