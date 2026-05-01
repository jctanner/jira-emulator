"""Integration smoke tests for the MCP server."""

import json
from contextlib import asynccontextmanager

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client


@asynccontextmanager
async def _mcp_session(url: str):
    async with sse_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


@pytest.mark.asyncio
async def test_mcp_list_tools(mcp_sse_url: str):
    async with _mcp_session(mcp_sse_url) as session:
        result = await session.list_tools()
        tool_names = {t.name for t in result.tools}
        expected = {
            "getJiraIssue",
            "searchJiraIssuesUsingJql",
            "createJiraIssue",
            "editJiraIssue",
            "addCommentToJiraIssue",
            "getTransitionsForJiraIssue",
            "transitionJiraIssue",
            "addAttachmentToJiraIssue",
            "getJiraIssueAttachments",
            "deleteJiraAttachment",
        }
        assert expected <= tool_names


@pytest.mark.asyncio
async def test_mcp_create_and_get_issue(mcp_sse_url: str, client: httpx.AsyncClient, auth_header: dict):
    async with _mcp_session(mcp_sse_url) as session:
        result = await session.call_tool(
            "createJiraIssue",
            {
                "projectKey": "TEST",
                "issueTypeName": "Bug",
                "summary": "Created via MCP",
            },
        )
        assert not result.isError
        data = json.loads(result.content[0].text)
        assert "key" in data

        key = data["key"]
        resp = await client.get(f"/rest/api/2/issue/{key}", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["fields"]["summary"] == "Created via MCP"


@pytest.mark.asyncio
async def test_mcp_search(mcp_sse_url: str):
    async with _mcp_session(mcp_sse_url) as session:
        await session.call_tool(
            "createJiraIssue",
            {
                "projectKey": "TEST",
                "issueTypeName": "Task",
                "summary": "MCP search target",
            },
        )

        result = await session.call_tool(
            "searchJiraIssuesUsingJql",
            {"jql": "project = TEST"},
        )
        assert not result.isError
        data = json.loads(result.content[0].text)
        assert data["total"] >= 1
