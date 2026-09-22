#!/usr/bin/env bash
set -euo pipefail
API_BASE="${API_BASE:-http://127.0.0.1:8001}"
for _ in $(seq 1 60); do
  if curl -fsS "$API_BASE/api/v1/health/ready" >/tmp/ytai-ready.json 2>/dev/null; then
    break
  fi
  sleep 2
done
curl -fsS "$API_BASE/api/v1/health/live" >/tmp/ytai-live.json
curl -fsS "$API_BASE/api/v1/health/ready" >/tmp/ytai-ready.json
python - <<'PY'
import json
ready=json.load(open('/tmp/ytai-ready.json'))
assert ready['status']=='ready', ready
print('staging_health=ok')
PY
