# Railway production deployment

The Railway production environment uses the `api-release` and `web-release` services for the application runtime.

The source of truth for application code is the `main` branch of this repository. Deployment verification must confirm that the running service commit matches the intended Git commit before a release is considered delivered.

The current project also contains a separate staged Railway service. Staged changes must not be applied as part of the application release unless they are explicitly intended.

For a production release, verify the API service deployment, readiness endpoint, and runtime logs after delivery.
