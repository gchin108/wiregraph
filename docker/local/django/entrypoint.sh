#!/bin/bash
set -o errexit
set -o pipefail
set -o nounset

# Wait for PostgreSQL to be ready
until python -c "
import psycopg
conn = psycopg.connect(
    dbname='${POSTGRES_DB}',
    user='${POSTGRES_USER}',
    password='${POSTGRES_PASSWORD}',
    host='${POSTGRES_HOST}',
    port='${POSTGRES_PORT}',
)
conn.close()
" 2>/dev/null; do
    echo "Waiting for PostgreSQL..."
    sleep 1
done
echo "PostgreSQL is ready!"

exec "$@"
