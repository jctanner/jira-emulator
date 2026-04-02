#!/bin/bash
# Import all JSON ticket files from a directory into the Jira emulator.
#
# Usage:
#   ./scripts/import-tickets.sh ./tickets
#   ./scripts/import-tickets.sh ./tickets http://127.0.0.1:9090 admin admin

set -euo pipefail

TICKET_DIR="${1:?Usage: $0 <ticket-dir> [base-url] [user] [password]}"
BASE_URL="${2:-http://127.0.0.1:8080}"
USER="${3:-admin}"
PASS="${4:-admin}"
BATCH_SIZE=50

if [ ! -d "$TICKET_DIR" ]; then
    echo "Error: directory not found: $TICKET_DIR" >&2
    exit 1
fi

FILES=("$TICKET_DIR"/*.json)
TOTAL=${#FILES[@]}

if [ "$TOTAL" -eq 0 ]; then
    echo "No .json files found in $TICKET_DIR" >&2
    exit 1
fi

echo "Importing $TOTAL tickets from $TICKET_DIR into $BASE_URL (batches of $BATCH_SIZE) ..."

IMPORTED=0
UPDATED=0
ERRORS=0

for (( i=0; i<TOTAL; i+=BATCH_SIZE )); do
    BATCH=("${FILES[@]:i:BATCH_SIZE}")
    BATCH_END=$(( i + ${#BATCH[@]} ))
    printf "\r  [%d-%d/%d] " "$((i+1))" "$BATCH_END" "$TOTAL"

    RESULT=$(jq -s '{issues: .}' "${BATCH[@]}" | \
        curl -s -X POST "$BASE_URL/api/admin/import" \
            -H "Content-Type: application/json" \
            -u "$USER:$PASS" \
            --max-time 120 \
            -d @-)

    B_IMPORTED=$(echo "$RESULT" | jq -r '.imported // 0')
    B_UPDATED=$(echo "$RESULT" | jq -r '.updated // 0')
    B_ERRORS=$(echo "$RESULT" | jq -r '.errors | length // 0')

    IMPORTED=$((IMPORTED + B_IMPORTED))
    UPDATED=$((UPDATED + B_UPDATED))
    ERRORS=$((ERRORS + B_ERRORS))

    printf "imported=%d updated=%d errors=%d\n" "$B_IMPORTED" "$B_UPDATED" "$B_ERRORS"

    if [ "$B_ERRORS" -gt 0 ]; then
        echo "$RESULT" | jq -r '.errors[]' | sed 's/^/    /'
    fi
done

echo ""
echo "Done: $IMPORTED imported, $UPDATED updated, $ERRORS errors"
