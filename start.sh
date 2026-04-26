#!/bin/bash
set -e

DB_PATH="${CREDENTIAL_DB:-/app/db/credentials.sqlite}"

if [ ! -f "$DB_PATH" ]; then
    mkdir -p "$(dirname "$DB_PATH")"

    if [ -n "$CREDENTIAL_DB_URL" ]; then
        echo "Downloading database from $CREDENTIAL_DB_URL ..."
        curl -fsSL "$CREDENTIAL_DB_URL" -o "$DB_PATH"
        echo "Download complete ($(du -sh "$DB_PATH" | cut -f1))."
    else
        echo "No CREDENTIAL_DB_URL set — building database from mock data..."
        python src/ingest.py --mock --db "$DB_PATH"
        echo "Mock database ready."
    fi
fi

exec uvicorn src.api:app --host 0.0.0.0 --port "${PORT:-8000}"
