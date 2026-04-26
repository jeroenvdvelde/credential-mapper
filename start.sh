#!/bin/bash
set -e

DB_PATH="${CREDENTIAL_DB:-/app/db/credentials.sqlite}"

if [ ! -f "$DB_PATH" ]; then
    mkdir -p "$(dirname "$DB_PATH")"

    echo "Building database from ESCO CSVs (this takes ~60s on first deploy)..."
    python src/ingest.py --langs en nl ar fr uk --db "$DB_PATH"
    echo "Database ready ($(du -sh "$DB_PATH" | cut -f1))."
fi

exec uvicorn src.api:app --host 0.0.0.0 --port "${PORT:-8000}"
