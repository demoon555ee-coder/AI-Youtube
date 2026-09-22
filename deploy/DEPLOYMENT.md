# Production deployment & disaster recovery

## Release contract

Application releases are immutable image references. CI must pass backend, frontend, integration, staging E2E, and release-audit gates before images are published. Release manifests hash critical runtime files and record the schema version. Database migrations are forward-only and must remain backward-compatible with the immediately previous application release (expand/contract). Schema rollback is not automatic.

## Blue/green deployment

The production application tier uses two isolated application slots:

- blue: API `127.0.0.1:8002`, web `127.0.0.1:3002`
- green: API `127.0.0.1:8003`, web `127.0.0.1:3003`

The database is shared. The inactive slot is upgraded and health-checked first. Traffic is switched only after local smoke tests pass. The previous slot remains available during the rollback window.

The reverse proxy configuration is rendered by `scripts/switch_slot.sh`. Set `PROXY_RELOAD_CMD` on the deployment host to the appropriate nginx reload command, for example `sudo nginx -t && sudo nginx -s reload`.

Run:

```bash
VERSION="$(python -c 'from app.config import settings; print(settings.app_version)')"
python scripts/create_release_manifest.py "$VERSION" -o RELEASE_MANIFEST.json
python scripts/verify_release_manifest.py RELEASE_MANIFEST.json --expected-tag "$VERSION"
scripts/deploy_blue_green.sh "$VERSION" RELEASE_MANIFEST.json .env.production docker-compose.bluegreen.yml
```

## Rollback

Rollback changes application images and proxy routing only. It never downgrades the database schema automatically.

```bash
scripts/rollback_blue_green.sh <previous-tag> <previous-manifest> .env.production docker-compose.bluegreen.yml
```

A rollback is safe only when the previous application release is compatible with the current schema. Use expand/contract migrations and keep destructive schema changes in a later release after dependent application versions are retired.

## Database backup

Every production deployment should take a database backup before migrations. The backup script writes:

- `.sql.gz` dump;
- `.sha256` checksum;
- `.json` backup metadata.

```bash
scripts/backup_database.sh .env.production docker-compose.production.yml
```

## Restore drill

A backup is not considered operationally trustworthy merely because `pg_dump` succeeded. Run the restore drill against a disposable PostgreSQL container:

```bash
scripts/restore_drill.sh ./backups/youtube_ai_<timestamp>.sql.gz postgres:16
```

The drill verifies checksum, gzip integrity, successful SQL restore, public table count, and restored `schema_migrations` version. It does not modify production data.

## CI/CD promotion

CI creates and verifies the release manifest. Production deployment is gated behind protected GitHub environments. Images are published only after integration and staging checks pass.

## Recovery principles

- application rollback: supported;
- database schema rollback: not automatic;
- data restore: performed into a controlled recovery target, then promoted after validation;
- production traffic: switched only after health and smoke checks;
- release state: recorded in `release_deployments` and deployment host state.
