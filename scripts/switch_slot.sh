#!/usr/bin/env bash
set -euo pipefail

SLOT="${1:-}"
STATE_FILE="${2:-./state/active_slot}"
PROXY_TEMPLATE="${3:-./deploy/nginx/youtube-ai-platform.conf.template}"
PROXY_TARGET="${4:-./state/active_proxy.conf}"
PROXY_RELOAD_CMD="${PROXY_RELOAD_CMD:-}"
ALLOW_UNRELOADED_PROXY="${ALLOW_UNRELOADED_PROXY:-false}"

if [[ "$SLOT" != "blue" && "$SLOT" != "green" ]]; then echo "slot must be blue or green" >&2; exit 2; fi
if [[ ! -f "$PROXY_TEMPLATE" ]]; then echo "missing proxy template: $PROXY_TEMPLATE" >&2; exit 2; fi
mkdir -p "$(dirname "$STATE_FILE")" "$(dirname "$PROXY_TARGET")"

case "$SLOT" in
  blue) API_PORT=8002; WEB_PORT=3002 ;;
  green) API_PORT=8003; WEB_PORT=3003 ;;
esac
sed -e "s/{{API_PORT}}/$API_PORT/g" -e "s/{{WEB_PORT}}/$WEB_PORT/g" "$PROXY_TEMPLATE" > "${PROXY_TARGET}.tmp"
mv "${PROXY_TARGET}.tmp" "$PROXY_TARGET"
printf '%s\n' "$SLOT" > "${STATE_FILE}.tmp"
mv "${STATE_FILE}.tmp" "$STATE_FILE"

if [[ -n "$PROXY_RELOAD_CMD" ]]; then
  bash -lc "$PROXY_RELOAD_CMD"
elif [[ "$ALLOW_UNRELOADED_PROXY" != "true" ]]; then
  echo "PROXY_RELOAD_CMD is required for an atomic traffic switch" >&2
  exit 2
fi

echo "active_slot=$SLOT"
