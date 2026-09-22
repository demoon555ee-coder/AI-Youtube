#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -f .env.staging ]]; then cp .env.staging.example .env.staging; fi
mkdir -p data/staging-output
exec docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build
