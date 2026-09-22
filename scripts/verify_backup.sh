#!/usr/bin/env bash
set -euo pipefail
BACKUP="${1:-}"
if [[ -z "$BACKUP" || ! -f "$BACKUP" ]]; then echo "usage: $0 <backup.sql.gz>" >&2; exit 2; fi
SHA_FILE="${BACKUP}.sha256"
if [[ ! -f "$SHA_FILE" ]]; then echo "missing checksum: $SHA_FILE" >&2; exit 2; fi
sha256sum -c "$SHA_FILE"
gzip -t "$BACKUP"
echo "backup_verified=true"
