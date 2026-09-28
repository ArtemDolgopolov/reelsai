#!/bin/sh
set -eu

SECRETS_DIR="${AUTH_SECRETS_DIR:-/var/lib/reelsai}"
SECRETS_FILE="${SECRETS_DIR}/secrets.env"
mkdir -p "$SECRETS_DIR"

ensure_secret() {
  # usage: ensure_secret VAR_NAME
  var_name="$1"
  eval "current=\${$var_name:-}"
  default_jwt="change-me-in-production-reelsai-auth-secret"
  default_pepper="change-me-otp-pepper"

  if [ -n "$current" ] && [ "$current" != "$default_jwt" ] && [ "$current" != "$default_pepper" ]; then
    return 0
  fi

  if [ -f "$SECRETS_FILE" ]; then
    # shellcheck disable=SC1090
    . "$SECRETS_FILE"
    eval "current=\${$var_name:-}"
    if [ -n "$current" ]; then
      export "$var_name=$current"
      return 0
    fi
  fi

  generated="$(python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"
  export "$var_name=$generated"
  touch "$SECRETS_FILE"
  # Replace or append
  if grep -q "^${var_name}=" "$SECRETS_FILE" 2>/dev/null; then
    sed -i "s|^${var_name}=.*|${var_name}=${generated}|" "$SECRETS_FILE"
  else
    echo "${var_name}=${generated}" >> "$SECRETS_FILE"
  fi
  echo "Generated persistent $var_name"
}

ensure_secret AUTH_JWT_SECRET
ensure_secret AUTH_OTP_PEPPER

echo "Waiting for PostgreSQL..."
python - <<'PY'
import os
import time
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
engine = create_engine(url, pool_pre_ping=True)
for attempt in range(60):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("PostgreSQL is ready")
        break
    except Exception as exc:
        print(f"Waiting ({attempt + 1}/60): {exc}")
        time.sleep(2)
else:
    raise SystemExit("PostgreSQL did not become ready in time")
PY

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
