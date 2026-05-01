#!/usr/bin/env bash
# Run integration tests against a real server stack managed by honcho.
# Usage: ./scripts/run-integration-tests.sh [pytest args...]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

export INTEGRATION_API_PORT="${INTEGRATION_API_PORT:-9876}"
export INTEGRATION_MCP_PORT="${INTEGRATION_MCP_PORT:-9877}"

TMPDIR="$(mktemp -d)"

cleanup() {
    echo ""
    echo "Cleaning up..."
    if [ -n "${HONCHO_PID:-}" ]; then
        kill -- -"$HONCHO_PID" 2>/dev/null || kill "$HONCHO_PID" 2>/dev/null || true
        wait "$HONCHO_PID" 2>/dev/null || true
    fi
    rm -rf "$TMPDIR"
    echo "Done."
}
trap cleanup EXIT

export DATABASE_URL="sqlite+aiosqlite:///${TMPDIR}/jira.db"
export AUTH_MODE="permissive"
export SEED_DATA="true"
export ATTACHMENT_DIR="${TMPDIR}/attachments"
export BASE_URL="http://localhost:${INTEGRATION_API_PORT}"

echo "=== Integration Test Runner ==="
echo "API port:  ${INTEGRATION_API_PORT}"
echo "MCP port:  ${INTEGRATION_MCP_PORT}"
echo "Database:  ${TMPDIR}/jira.db"
echo ""

cd "$PROJECT_DIR"

echo "Starting servers via honcho..."
setsid uv run honcho start -f Procfile.integration &
HONCHO_PID=$!

echo "Waiting for API server..."
for i in $(seq 1 30); do
    if curl -sf -u "admin:admin" \
        "http://localhost:${INTEGRATION_API_PORT}/rest/api/2/priority" >/dev/null 2>&1; then
        echo "API server ready."
        break
    fi
    if ! kill -0 "$HONCHO_PID" 2>/dev/null; then
        echo "ERROR: honcho process died." >&2
        exit 1
    fi
    sleep 1
done

if ! curl -sf -u "admin:admin" \
    "http://localhost:${INTEGRATION_API_PORT}/rest/api/2/priority" >/dev/null 2>&1; then
    echo "ERROR: API server failed to start within 30 seconds." >&2
    exit 1
fi

sleep 2
if ! kill -0 "$HONCHO_PID" 2>/dev/null; then
    echo "ERROR: honcho process died after MCP server start." >&2
    exit 1
fi
echo "MCP server ready."
echo ""

echo "Running integration tests..."
uv run pytest tests/integration/ -x -v "$@"
