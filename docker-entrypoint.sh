#!/bin/sh
set -e

: "${APP_MODULE:=demo_app:app}"
: "${HOST:=0.0.0.0}"
: "${PORT:=8000}"
: "${WORKERS:=1}"

if [ $# -gt 0 ]; then
    exec "$@"
fi

exec fenrir run "$APP_MODULE" -H "$HOST" -p "$PORT" -w "$WORKERS"