#!/usr/bin/env bash
#
# Start the application for the Playwright suite.
#
# Uses a scratch SQLite database under .e2e/ rather than the configured
# DATABASE_URL, so running the E2E suite can never touch a real library. The
# database is recreated on every start, which is what lets the specs assume
# they begin with zero users and hit the first-run registration flow.
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${E2E_PORT:-8099}"
E2E_DIR="$PWD/.e2e"

rm -rf "$E2E_DIR"
mkdir -p "$E2E_DIR"/{audiobooks,covers,auth,temp,logs}

# The SPA is served by the app itself from app/static/spa, so it has to exist
# before the server starts. Skipped when it is already newer than the sources.
if [ ! -f app/static/spa/index.html ] || [ -n "$(find frontend/src -newer app/static/spa/index.html -print -quit 2>/dev/null)" ]; then
  echo "Building SPA..."
  (cd frontend && npm run build)
fi

PYTHON="${PYTHON:-.venv/bin/python}"

export ENVIRONMENT=testing
export DATABASE_URL="sqlite:///$E2E_DIR/e2e.db"
export SECRET_KEY="e2e-secret-key-not-for-production"
export DOMAIN="http://127.0.0.1:$PORT"
export AUDIOBOOKS_PATH="$E2E_DIR/audiobooks"
export COVERS_PATH="$E2E_DIR/covers"
export AUDIBLE_AUTH_PATH="$E2E_DIR/auth"
export TEMP_PATH="$E2E_DIR/temp"
# No SMTP: magic links are read out of the database by the test helper instead
# of being delivered, so nothing tries to reach a mail server.
export SMTP_HOST=""
export SMTP_USER=""
export SMTP_PASSWORD=""
export SMTP_FROM=""

# init_db() is skipped when ENVIRONMENT=testing, so create the schema here.
"$PYTHON" - <<'PY'
from app.database import Base, engine
import app.models  # noqa: F401 -- registers the tables on Base
Base.metadata.create_all(bind=engine)
print("E2E schema created")
PY

exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning
