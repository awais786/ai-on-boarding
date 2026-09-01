#!/usr/bin/env bash
# Run the API behaviour verification end to end.
#
# This is the whole chain: generate the description, prove coverage complete,
# start the mail catcher and the server, build the collection, execute it, and
# leave the report where the gate and the evaluation can read it. The workflow
# runs this same script, so a failure in CI reproduces here with one command.
#
# Exits non-zero only on a setup failure. Whether the run passes is the gate's
# decision, not this script's - it needs the evaluation's findings too.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
BUILD="$HERE/build"
PYTHON="${PYTHON:-$HERE/.venv/bin/python}"
NEWMAN="$HERE/node_modules/.bin/newman"
CONVERTER="$HERE/node_modules/.bin/openapi2postmanv2"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
MAIL_SMTP_PORT="${MAIL_SMTP_PORT:-1025}"
MAIL_HTTP_PORT="${MAIL_HTTP_PORT:-8025}"
BASE_URL="http://${API_HOST}:${API_PORT}"
MAIL_BASE_URL="http://${API_HOST}:${MAIL_HTTP_PORT}"
# Letters, digits and underscores only, and kept short: the token goes into
# usernames as well as addresses, and "Enforce a username format" allows no
# other character and caps the whole username at 30.
RUN_TOKEN="${RUN_TOKEN:-$(date +%s | tail -c 7)_${RANDOM}}"

mkdir -p "$BUILD"
export PYTHONPATH="$REPO/sdd_django_demo:$HERE"
export DJANGO_SETTINGS_MODULE="verify.run_settings"

server_pid=""
mail_pid=""
cleanup() {
  [ -n "$server_pid" ] && kill "$server_pid" 2>/dev/null || true
  [ -n "$mail_pid" ] && kill "$mail_pid" 2>/dev/null || true
}
trap cleanup EXIT

wait_for() {  # wait_for <url> <what>
  for _ in $(seq 1 60); do
    if curl -fsS -o /dev/null "$1" 2>/dev/null; then return 0; fi
    sleep 0.5
  done
  echo "Timed out waiting for $2 at $1" >&2
  return 1
}

echo "==> Generating the OpenAPI description"
# Not run in a mode that treats generation errors as fatal: the description
# cannot infer a response shape for the health endpoint, and no promoted
# requirement depends on that shape.
"$PYTHON" -m django spectacular --file "$BUILD/schema.yaml"

echo "==> Checking coverage is complete against the routed addresses"
"$PYTHON" -m verify.completeness --schema "$BUILD/schema.yaml" --surfaces "$HERE/surfaces.yaml"

echo "==> Deriving the collection from the description"
"$CONVERTER" -s "$BUILD/schema.yaml" -o "$BUILD/derived.json" -p >/dev/null

echo "==> Building the collection with its checks attached"
"$PYTHON" -m verify.build --schema "$BUILD/schema.yaml" --out "$BUILD/collection.json"

echo "==> Starting the mail catcher"
# A run starts from an empty database by default. Set KEEP_DB=1 to run against
# whatever the last run left behind - every sequence addresses accounts carrying
# a per-run token, so a repeat run must produce the same outcomes either way.
[ -n "${KEEP_DB:-}" ] || rm -f "$BUILD/verification.sqlite3"
mailpit --smtp "${API_HOST}:${MAIL_SMTP_PORT}" --listen "${API_HOST}:${MAIL_HTTP_PORT}" \
  >"$BUILD/mailpit.log" 2>&1 &
mail_pid=$!
wait_for "$MAIL_BASE_URL/api/v1/info" "the mail catcher"

echo "==> Starting the API"
"$PYTHON" -m django migrate --noinput >"$BUILD/migrate.log" 2>&1
RESET_SMTP_HOST="$API_HOST" \
RESET_SMTP_PORT="$MAIL_SMTP_PORT" \
RESET_SMTP_TLS=0 \
  "$PYTHON" -m django runserver "${API_HOST}:${API_PORT}" --noreload \
  >"$BUILD/server.log" 2>&1 &
server_pid=$!
wait_for "$BASE_URL/api/health/" "the API"

echo "==> Executing the collection"
# Removed before the run, not after: a runner that aborts before writing a
# report would otherwise leave the previous run's results on disk for the gate
# to grade, reporting a pass for a run that produced nothing.
rm -f "$BUILD/report.json" "$BUILD/findings.json"
set +e
"$NEWMAN" run "$BUILD/collection.json" \
  --reporters cli,json \
  --reporter-json-export "$BUILD/report.json" \
  --env-var "baseUrl=$BASE_URL" \
  --env-var "mailBaseUrl=$MAIL_BASE_URL" \
  --env-var "runToken=$RUN_TOKEN" \
  --timeout-request 15000 \
  --suppress-exit-code
newman_status=$?
set -e

if [ ! -f "$BUILD/report.json" ]; then
  echo "The collection runner exited ${newman_status} without writing a report." >&2
  echo "There are no results to grade; failing rather than leaving the gate to" >&2
  echo "decide on an absent or stale file." >&2
  exit 1
fi

echo "==> Report written to $BUILD/report.json (newman exit ${newman_status})"
echo "    Whether this run passes is decided by verify.gate."
