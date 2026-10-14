# Safe local development and verification

Read the root and application `AGENTS.md`, inspect `git status --short` and the
relevant diff, then implement only the requested change. Do not use `make up`,
`make test`, `make migrate`, private environment files, or existing application
containers as shortcuts for isolated verification.

## Prerequisites

- Docker Engine/Desktop and Compose v2 for Python 3.12, FFmpeg and PostgreSQL 17.6.
- Node >=20.9 and npm for the web application; Node 22 matches its Dockerfile.
- Install web dependencies with `cd apps/web && npm ci` when absent or when the
  lockfile changes. Existing dependencies do not need reinstalling each run.
- Initial container builds and Google font downloads need Internet access. No
  paid service or real provider credential is required.

Before starting Docker Desktop, check whether it will automatically restart
existing containers. Docker restart policies can resume messaging workers even
without `make up`. Do not start a daemon managing real customer integrations.
The verification commands do not start, inspect or stop unrelated containers.

## Backend tests

From the repository root:

```bash
make verify-api
```

This builds the existing API Dockerfile and runs pytest against a fresh PostgreSQL
instance. The fixed `tkila-verify` Compose project uses only
`docker-compose.verify.yml`, ignores automatic `.env` loading, publishes no test
DB ports, mounts no host directories, and stores database files in tmpfs. Runtime
containers use an internal network without Internet access. Re-running the target
recreates only the test database container. The runner waits for PostgreSQL, runs
a one-off pytest container, propagates its exit code, and stops the test database
on exit. It does not use Compose abort-on-container-exit, which can react to other
container exits in the project. Run one verification per checkout at a time;
this fixed project name is not designed for concurrent agents.

Pytest refuses to connect unless `TEST_DATABASE_URL` explicitly names a
`postgresql+psycopg` database ending in `_test` on localhost, loopback or `db-test`,
with no URL query overrides and `TKILA_TEST_ALLOW_RESET=1`. This guard is a
mistake-prevention measure, not proof that an arbitrary local database is safe.
The Compose target provides the disposable database and explicit reset consent.
Tests reset tables before/after each test; they never delete a database.

Before importing the application, pytest disables dotenv loading, removes inherited
application settings and supplies a temporary attachment directory. Workers and
automatic conversation resolution are disabled. Never add live credentials to tests.
For a host-run suite, separately prevent outbound network access; only the Compose
path provides network isolation. Mocked integrations do not establish real delivery.

For targeted checks, the same runner accepts pytest arguments:

```bash
bash scripts/verify-api.sh -q tests/test_flows.py::test_register_login_logout_and_me
```

The guard can also be tested without connecting to a database, inside the built image:

```bash
docker run --rm --network none tkila-verify-api-test python -m unittest discover -s tests -p test_database_safety.py
```

## Frontend checks

```bash
make verify-web
# Equivalent individual commands, inside apps/web:
npm run lint
npm run typecheck
npm run build
# If Turbopack cannot open its local worker port in a restricted environment:
npm run build:webpack
# Or from the repository root:
make verify-web WEB_BUNDLER_FLAGS=--webpack
```

`verify-web` fails if any stage fails. The fallback is explicit: it does not hide
a failing Turbopack build. Both builds may download the existing Google fonts.
Do not substitute fake fonts or claim an offline build passed. Check `node --version`
first; this host also has `/usr/local/bin/node` v24.14.1, while its default NVM PATH
selects v18.20.8. `PATH=/usr/local/bin:$PATH make verify-web` selects the supported
installed runtime here; this absolute path is not a portable prerequisite.

## Local application preview and migrations

```bash
make preview-api
make preview-web
# Optional fallback on restricted hosts:
make preview-web WEB_BUNDLER_FLAGS=--webpack
```

The browser UI is at `http://localhost:13000`, and the API at
`http://localhost:18000` (`/health` and `/docs` are available). The frontend binds
to loopback and explicitly points at this preview API. Use invented test accounts
and data only. The API has a separate tmpfs PostgreSQL database, disabled social
and resolution workers, no push provider, no bridge, and no Internet access.
A Caddy gateway joins the internal network and a separate edge network to expose
only the loopback API port; the API and database remain exclusively on the internal
network. The gateway forwards inbound requests only to the preview API.
By default AI, messaging and external tools cannot be acceptance-tested here.
For explicitly authorized local Ollama tests, `make preview-api-ollama` adds a
restricted gateway to the Mac: use `http://ollama-preview:11434` in Settings.
It permits only model discovery, capability checks and chat. No messaging bridge
or general Internet access is added. See [agent-builder.md](agent-builder.md).

The API's existing startup applies all Alembic migrations before serving requests.
On the first preview start the database is empty, which validates the upgrade path
independently of pytest's model-created schema. Inspect it with:

```bash
docker compose --env-file /dev/null -p tkila-verify -f docker-compose.verify.yml logs api-preview
docker compose --env-file /dev/null -p tkila-verify -f docker-compose.verify.yml exec -T api-preview alembic current
```

API source and migrations are mounted read-only. After Python-only changes,
restart just `api-preview`; use the same Ollama override file when applicable.
For dependency changes, rerun `make preview-api` (or `make preview-api-ollama`)
to rebuild. `PREVIEW_BUILD_FLAGS=--no-build` explicitly reuses a cached image. A stopped/recreated preview
DB loses its synthetic data. Never use it to store work you need to retain. The
preview uses the application's existing development-only defaults, not production
secrets or production hardening. To clean up only this disposable project:

```bash
make verify-api-stop
```

Stop the foreground web process with Ctrl-C. `next dev` may regenerate the tracked
`apps/web/next-env.d.ts` to reference `.next/dev/types`; inspect this generated diff
and avoid including it in unrelated changes. Do not run `make destroy`.

## Delivery loop

Inspect the task and code → implement → run the applicable checks → diagnose
failures → correct scoped issues → rerun affected checks → inspect the final diff.
Report actual check results, pre-existing warnings, blocked checks and remaining
risks. Do not equate a build, mocked test suite or fresh-schema migration with
production readiness. Go bridge and native mobile checks remain separate; they
need their declared toolchains and must not connect to existing messaging stores.
