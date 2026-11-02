# Deploy Dibsly

## Production package

Use a Linux host with Docker Compose, at least 3 GB of available RAM for the supplied containers, and a domain pointing to the host. This is a starting resource allocation, not a traffic-capacity guarantee. Open inbound ports 80 and 443 for Caddy's HTTPS certificate flow.

1. Copy `.env.example` to `.env`.
2. Set `SITE_ADDRESS` to your real domain and set three unique secrets: `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD`, and `ADMIN_PASSWORD` (at least 12 characters).
3. Run `docker compose config --quiet` to validate substitution without printing secrets.
4. Run `docker compose up -d --build`.
5. Check `docker compose ps`, then visit `https://YOUR_DOMAIN/health`, `/`, `/register`, and `/login`.
6. Create one client and two freelancer accounts and run a complete project/pitch/hire/completion smoke test. Verify that one freelancer cannot read the other's offer.

The build runs Java tests. The database and application aren't published directly to the host; Caddy forwards web requests. Secure cookies are enabled. MySQL is reached over the private Docker network; use TLS for a database outside that trusted network. The application refuses production mode without a MySQL URL and password, or when demo seeding is enabled.

## First deployment versus existing data

Production starts with an empty marketplace and a bootstrap administrator. `ADMIN_PASSWORD` only creates a missing admin; changing the environment value does not reset an existing account. Demo usernames/passwords never seed production.

This project copy does not migrate the original Eclipse database. Its schema initialization creates missing tables; it is not a general migration engine. Back up and review schema/data migration before pointing at any existing database. Do not use the original ResolveBid database as a production shortcut.

## Operations

- `/health` checks database availability and returns 200 or 503.
- MySQL, app runtime data, and Caddy certificate state have named volumes. Back up the MySQL database and verify a restore before admitting real data. Volume persistence alone is not a backup.
- Logs rotate at 10 MB with three retained files per container.
- Stop/update with `docker compose down` and `docker compose up -d --build`; do not add `--volumes` unless deliberately discarding stored data.
- Pin image digests after validating the exact deployment, run dependency/container scanning, monitor failures and latency, and maintain OS/TLS updates.
- For a non-container deployment, `java -jar target/dibsly-1.0.0.jar` reads `APP_ENV`, `DB_URL`, `DB_USER`, `DB_PASSWORD`, `PORT`, `SECURE_COOKIES`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD` from the environment. `.env` is consumed by Compose, not automatically by Java.

## Scale boundary

The current release supports a single application instance with a bounded Tomcat connector (80 request threads, 1,024 connections, 32 KB form bodies), paginated public listings, and row-level transactional writes. It does not yet provide connection pooling, a distributed session store, shared rate limits, search indexing, asynchronous queues, or a tested horizontal deployment. The workspace shows the latest 100 projects; admin access management shows up to 100 accounts.

Before scaling out, introduce a JDBC connection pool, shared sessions and abuse controls, versioned schema migrations, appropriate query indexes, and measured load tests against representative data. Dibsly authorization uses account-row locks in a shared database. Its current local tests do not establish a distributed deployment's behavior; validate the target database, connection settings, failure handling, and all guarded paths before scaling.

## Verification status

See `VERIFICATION.md` for what was actually run. Docker/MySQL and public TLS require a live target environment. They are not certified by a successful H2 test or a successful local JAR launch.
