#!/bin/sh
set -eu

python - <<'PY'
import os
import socket
import time

host = os.getenv("DB_IP", "db")
port = int(os.getenv("DB_PORT", "5432"))
deadline = time.time() + 60

while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=3):
            break
    except OSError:
        time.sleep(2)
else:
    raise SystemExit(f"Database is not reachable at {host}:{port}")
PY

exec "$@"
