#!/usr/bin/env bash
set -euo pipefail

TAG="${1:-}"
MANIFEST="${2:-}"
ENV_FILE="${3:-.env.production}"
COMPOSE_FILE="${4:-docker-compose.bluegreen.yml}"
STATE_FILE="${ACTIVE_SLOT_FILE:-./state/active_slot}"
PUBLIC_SMOKE_URL="${PUBLIC_SMOKE_URL:-}"
ROLLBACK_WINDOW_SECONDS="${ROLLBACK_WINDOW_SECONDS:-30}"
: "${PROXY_RELOAD_CMD:?PROXY_RELOAD_CMD must be configured for production traffic switching}"

if [[ -z "$TAG" || -z "$MANIFEST" ]]; then
  echo "usage: $0 <release-tag> <manifest> [env-file] [compose-file]" >&2
  exit 2
fi
[[ -f "$ENV_FILE" ]] || { echo "missing env file: $ENV_FILE" >&2; exit 2; }
[[ -f "$MANIFEST" ]] || { echo "missing manifest: $MANIFEST" >&2; exit 2; }
./scripts/verify_release_manifest.py "$MANIFEST" --expected-tag "$TAG"

CURRENT=""
[[ -f "$STATE_FILE" ]] && CURRENT="$(tr -d '[:space:]' < "$STATE_FILE")"
if [[ "$CURRENT" == "blue" ]]; then TARGET=green; elif [[ "$CURRENT" == "green" ]]; then TARGET=blue; else TARGET=blue; fi

export RELEASE_TAG="$TAG"
export RELEASE_MANIFEST="$MANIFEST"
export BLUE_GREEN_TARGET="$TARGET"
API_IMAGE_REF="${API_IMAGE_REF:-$(python - <<'PY'
import json
from pathlib import Path
m=json.loads(Path("$RELEASE_MANIFEST").read_text())
print(m.get("api_image_ref") or "")
PY
)}"
WEB_IMAGE_REF="${WEB_IMAGE_REF:-$(python - <<'PY'
import json
from pathlib import Path
m=json.loads(Path("$RELEASE_MANIFEST").read_text())
print(m.get("web_image_ref") or "")
PY
)}"
if [[ -z "$API_IMAGE_REF" || -z "$WEB_IMAGE_REF" ]]; then
  echo "manifest must contain digest-pinned api_image_ref and web_image_ref" >&2
  exit 2
fi
export API_IMAGE_REF WEB_IMAGE_REF

echo "active=$CURRENT target=$TARGET release=$TAG"

if [[ "${SKIP_BACKUP:-false}" != "true" ]]; then
  ./scripts/backup_database.sh "$ENV_FILE" docker-compose.production.yml
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull api_blue api_green web_blue web_green migrate

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" run --rm migrate

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-deps "api_$TARGET" "web_$TARGET"

API_PORT=$([[ "$TARGET" == "blue" ]] && echo 8002 || echo 8003)
WEB_PORT=$([[ "$TARGET" == "blue" ]] && echo 3002 || echo 3003)
for _ in $(seq 1 45); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/api/v1/health/ready" >/dev/null && curl -fsS "http://127.0.0.1:${WEB_PORT}" >/dev/null; then
    break
  fi
  sleep 2
done
curl -fsS "http://127.0.0.1:${API_PORT}/api/v1/health/ready" >/dev/null
curl -fsS "http://127.0.0.1:${WEB_PORT}" >/dev/null

./scripts/switch_slot.sh "$TARGET" "$STATE_FILE"
if [[ -n "$PUBLIC_SMOKE_URL" ]]; then curl -fsS "$PUBLIC_SMOKE_URL" >/dev/null; fi

if [[ -n "$CURRENT" && "${KEEP_OLD_SLOT:-false}" != "true" ]]; then
  sleep "$ROLLBACK_WINDOW_SECONDS"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" stop "api_$CURRENT" "web_$CURRENT" || true
fi

docker compose --env-file "$ENV_FILE" -f docker-compose.production.yml up -d --no-deps worker

echo "deployment_complete=true"
echo "active_slot=$TARGET"
