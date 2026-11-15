#!/usr/bin/env bash
# Run integration tests against a live API server and MCP server.
# Usage: ./scripts/run-integration-tests.sh [pytest args...]
#
# The servers are started directly, not through honcho. Under Python 3.14,
# multiprocessing defaults to the forkserver start method, so honcho's
# process runners are not in honcho's process group, and `uv run` puts each
# server in its own session. Signalling honcho's group therefore missed the
# servers, and honcho could crash on teardown ("reentrant call inside
# <_io.BufferedWriter name='<stdout>'>"), leaving them running and holding
# the caller's output pipe open. Tracking the server PIDs here avoids both.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

export INTEGRATION_API_PORT="${INTEGRATION_API_PORT:-9876}"
export INTEGRATION_MCP_PORT="${INTEGRATION_MCP_PORT:-9877}"

TMPDIR="$(mktemp -d)"
SERVER_PIDS=()

stop_servers() {
    local pid
    for pid in "${SERVER_PIDS[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    # Give uvicorn a graceful shutdown, then force anything still running.
    for _ in $(seq 1 10); do
        local alive=0
        for pid in "${SERVER_PIDS[@]}"; do
            kill -0 "$pid" 2>/dev/null && alive=1
        done
        [ "$alive" -eq 0 ] && break
        sleep 1
    done
    for pid in "${SERVER_PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "Server $pid did not stop after SIGTERM; sending SIGKILL." >&2
            kill -KILL "$pid" 2>/dev/null || true
        fi
        wait "$pid" 2>/dev/null || true
    done
}

show_logs() {
    local log
    for log in "$TMPDIR"/api.log "$TMPDIR"/mcp.log; do
        [ -f "$log" ] || continue
        echo "--- $(basename "$log") (last 40 lines) ---" >&2
        tail -n 40 "$log" >&2
    done
}

cleanup() {
    echo ""
    echo "Cleaning up..."
    stop_servers
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

# Resolve the project interpreter once, so the PIDs below are the servers
# themselves rather than `uv run` wrappers.
PYTHON="$(uv run python -c 'import sys; print(sys.executable)')"

echo "Starting servers..."
"$PYTHON" -m jira_emulator serve --port "$INTEGRATION_API_PORT" >"$TMPDIR/api.log" 2>&1 &
API_PID=$!
SERVER_PIDS+=("$API_PID")

JIRA_SERVER="http://localhost:${INTEGRATION_API_PORT}" JIRA_USER=admin JIRA_TOKEN=admin \
    MCP_PORT="$INTEGRATION_MCP_PORT" \
    "$PYTHON" mcp_servers/atlassian_jira.py >"$TMPDIR/mcp.log" 2>&1 &
MCP_PID=$!
SERVER_PIDS+=("$MCP_PID")

http_status() {
    # Print the HTTP status for a URL. The SSE endpoint streams forever, so a
    # timeout after the headers arrive still reports their status code.
    curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$@" || true
}

wait_for() {
    local name="$1" pid="$2"
    shift 2
    for _ in $(seq 1 30); do
        if [ "$(http_status "$@")" = "200" ]; then
            echo "$name server ready."
            return 0
        fi
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "ERROR: $name server exited during startup." >&2
            show_logs
            exit 1
        fi
        sleep 1
    done
    echo "ERROR: $name server failed to start within 30 seconds." >&2
    show_logs
    exit 1
}

echo "Waiting for API server..."
wait_for API "$API_PID" -u "admin:admin" "http://localhost:${INTEGRATION_API_PORT}/rest/api/2/priority"
echo "Waiting for MCP server..."
wait_for MCP "$MCP_PID" "http://localhost:${INTEGRATION_MCP_PORT}/sse"
echo ""

echo "Running integration tests..."
uv run pytest tests/integration/ -x -v "$@"
