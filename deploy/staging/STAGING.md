# Staging environment

Staging intentionally uses real PostgreSQL but safe mock AI/billing providers and no Google OAuth credentials.

## Local

```bash
cp .env.staging.example .env.staging
./scripts/staging_up.sh
./scripts/staging_smoke.sh
cd e2e
npm install --no-audit --no-fund
npx playwright install --with-deps chromium
npm run test
```

Tear down with:

```bash
./scripts/staging_down.sh
```

## Gate

The main CI workflow runs the browser suite after backend, frontend and PostgreSQL integration jobs. Docker image publication waits for the staging E2E job.

Staging data is disposable and the compose teardown removes its PostgreSQL volume.
