# Browser E2E

The staging browser suite validates the critical creator flow against a real PostgreSQL-backed stack:

`register → channel → ideas → project → workflow → FFmpeg render → MP4 + thumbnail`

Run the stack first:

```bash
cp .env.staging.example .env.staging
./scripts/staging_up.sh
./scripts/staging_smoke.sh
```

Then run Playwright:

```bash
cd e2e
npm install --no-audit --no-fund
npx playwright install --with-deps chromium
npm run test
```
