# Security & Privacy Controls — v2.9

## Browser session security

- Browser sessions use an HttpOnly, Secure cookie in production.
- Production deployments require an `__Host-` session cookie name with `Path=/` and no Domain attribute.
- State-changing requests made with a browser session require the per-session CSRF token in `X-CSRF-Token`.
- When present, the request `Origin` header must match an explicit configured CORS origin.
- API-key authenticated requests use scoped bearer credentials and are not subject to browser CSRF checks.

## Credential protection

- Passwords are stored as salted PBKDF2-SHA256 hashes.
- YouTube OAuth credentials are encrypted at rest using Fernet.
- Encryption rotation supports a current + previous key window. Run `scripts/rotate_encryption_keys.py` after deploying a new current key, then remove the previous key after verification.
- Raw API keys are returned only once at creation/rotation; only a one-way hash and short prefix are stored.
- Audit metadata is centrally redacted for sensitive keys such as tokens, passwords, secrets and authorization headers.

## Abuse controls

- Login attempts are rate-limited using hashed email + client-IP keys.
- Five failures in a rolling 15-minute window trigger a 15-minute block for that key.
- Successful login clears the login failure record.
- Production configuration rejects development authentication fallback and wildcard CORS.

## Privacy controls

The product includes operational controls for common GDPR data-subject workflows. These controls do not by themselves constitute legal compliance; the final legal basis, notices, retention periods, processor terms and organizational procedures must be configured for the deployment.

Available controls:

- Personal data export from `/api/v1/privacy/export`.
- Erasure request with password re-authentication.
- Background processing of erasure requests.
- Anonymization of the user's identity and revocation of credentials.
- Removal of direct actor/user references from retained audit and usage events during erasure.
- Retention cleanup for audit, usage, revoked sessions, login-rate-limit state and completed privacy requests.

Organization-owned content is intentionally not silently deleted by the personal-account erasure worker.

## Browser hardening

The API and frontend set CSP, clickjacking, MIME-sniffing, referrer, permissions and HSTS-related headers appropriate to their deployment role.

The frontend CSP is intentionally constrained to the configured API origin for network calls. Any new third-party browser dependency must be explicitly added to the CSP.

## Operational requirements

Before production rollout:

1. Configure HTTPS URLs and explicit CORS origins.
2. Set a strong `APP_ENCRYPTION_KEY`.
3. Use `__Host-youtube_ai_session` for `AUTH_COOKIE_NAME`.
4. Configure real billing and webhook secrets.
5. Run the database migration gate.
6. Run the encryption rotation procedure when changing the Fernet key.
7. Test backup restore and staging E2E in CI.
8. Review retention values with legal/accounting requirements before enabling automatic cleanup.
