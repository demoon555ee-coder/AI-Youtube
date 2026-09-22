#!/usr/bin/env bash
set -euo pipefail
BACKUP="${1:-}"
POSTGRES_IMAGE="${2:-postgres:16}"
if [[ -z "$BACKUP" || ! -f "$BACKUP" ]]; then echo "usage: $0 <backup.sql.gz> [postgres-image]" >&2; exit 2; fi
./scripts/verify_backup.sh "$BACKUP"
gzip -t "$BACKUP"
NAME="youtube-ai-restore-drill-$$"
docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=restore_drill "$POSTGRES_IMAGE" >/dev/null
cleanup(){ docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT
for _ in $(seq 1 60); do
  if docker exec "$NAME" pg_isready -U postgres -d restore_drill >/dev/null 2>&1; then break; fi
  sleep 1
done
docker exec -i "$NAME" psql -U postgres -d restore_drill < <(gzip -dc "$BACKUP") >/dev/null
TABLES="$(docker exec "$NAME" psql -U postgres -d restore_drill -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
MIGRATION="$(docker exec "$NAME" psql -U postgres -d restore_drill -Atc "SELECT COALESCE((SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1),'none')")"
python - "$BACKUP" "$TABLES" "$MIGRATION" <<'PY'
import json,sys
from pathlib import Path
backup,tables,migration=sys.argv[1:]
out=Path(backup).with_suffix('.restore-drill.json')
out.write_text(json.dumps({'backup':backup,'public_table_count':int(tables),'schema_version':migration,'status':'PASS'},indent=2)+'\n')
print(f'restore_drill=PASS tables={tables} schema={migration}')
PY
