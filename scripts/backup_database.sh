#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env.production}"
COMPOSE_FILE="${2:-docker-compose.production.yml}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT="${3:-./backups/youtube_ai_${STAMP}.sql.gz}"

if [[ ! -f "$ENV_FILE" ]]; then echo "missing env file: $ENV_FILE" >&2; exit 2; fi
mkdir -p "$(dirname "$OUTPUT")"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db pg_dump -U "$(grep '^POSTGRES_USER=' "$ENV_FILE" | cut -d= -f2-)" -d "$(grep '^POSTGRES_DB=' "$ENV_FILE" | cut -d= -f2-)" | gzip -9 > "$OUTPUT"
sha256sum "$OUTPUT" > "${OUTPUT}.sha256"
cat > "${OUTPUT}.json" <<EOF
{
  "backup": "$(basename "$OUTPUT")",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "release_id": "${RELEASE_ID:-unknown}",
  "release_tag": "${RELEASE_TAG:-unknown}",
  "format": "pg_dump_plain_sql_gzip",
  "checksum_file": "$(basename "$OUTPUT").sha256"
}
EOF
echo "backup=$OUTPUT"
echo "checksum=${OUTPUT}.sha256"
