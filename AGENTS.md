# Tkila Box agent manual

## Product and scope

Tkila Box is being developed into a SaaS for business automation and AI agents.
Agencies manage business clients, their agents, messaging channels, and human
operators. The product builds on OpenLivery; the repository already contains a
substantial messaging platform, but the Tkila Box branding and broader SaaS
features are incomplete. Never describe a marketing preview as a working feature.

This file is the persistent repository manual. `CLAUDE.md` points here. Read any
app-specific `AGENTS.md` before working in that app. Implementation and manifests
are the source of truth when older documentation disagrees. Recheck audit findings
before acting on them, and update this manual when relevant behavior changes.

## Permanent operating rules

- Inspect related code, configuration, tests, and Git changes before implementing.
- Do not invent APIs, routes, tables, environment variables, dependencies, or results.
- Reuse existing architecture, components, services, and typed interfaces where
  appropriate. Avoid duplicated logic and unrelated or unnecessary large refactors.
- You may create, edit, or remove project code when needed for the task. First
  establish the purpose of existing code and work; do not discard others' changes.
- Preserve compatibility unless the task explicitly requires a breaking change.
- Prefer small, reviewable, verifiable changes.
- Run applicable tests, lint, type checks, and builds after changes. Fix failures
  introduced by your work and verify again. Never claim completion when you know
  the code is broken. Report unavailable checks and pre-existing failures honestly.
- Never deploy or publish to production automatically.
- Never delete databases or modify real customer data.
- Never expose secrets, tokens, passwords, or private `.env` contents in output,
  logs, commits, documentation, or examples. Use documented example files to learn
  configuration. Do not rotate existing encryption keys as routine maintenance.
- Never purchase services or incur costs without explicit authorization. Live AI,
  messaging, and hosted build calls can incur costs; use isolated fixtures and
  mocks unless live usage is explicitly authorized.
- Request approval before destructive or irreversible operations. Approval does
  not waive the prohibitions on deleting databases or changing real customer data.
- Respect existing Git changes. Never run `git reset --hard`, force-push, or
  overwrite another person's work. Do not stage or commit unrelated changes.

Workflow: analyze -> plan -> implement -> execute/verify -> correct errors ->
verify again -> document the result.

At the end of each task briefly report what changed, the main files modified,
checks executed, their results, remaining problems, and the recommended next step.

## Real architecture

Four application directories; Docker Compose starts five services: `db`, `api`,
`web`, `whatsapp`, and `proxy`. Mobile is optional and built separately.

- Browser -> Caddy -> Next.js pages or FastAPI `/api/*` routes.
- FastAPI -> PostgreSQL, local attachment storage, AI providers, external tools,
  and messaging providers. Background processing runs inside the API process.
- WhatsApp QR uses a stateful Go/whatsmeow bridge authenticated with a shared token.
- WhatsApp Cloud, Instagram, and Messenger integrate with Meta APIs and webhooks.
- The mobile application uses the portal/mobile API with bearer authentication.
- Inbox, portal, widget, and mobile refresh through polling; do not assume a
  WebSocket or streaming event infrastructure exists.

### Data and authentication boundaries

`apps/api/app/models.py` defines the current SQLAlchemy model:

- Agency -> users, clients, provider credentials.
- Client -> agents, channels, contacts, conversations, portal users, teams.
- Agent -> knowledge documents/chunks, Q&A, tools, escalation rules.
- Conversation -> messages, attachments, assignment, lifecycle and delivery state.
- Social channels -> OAuth state, webhook events, outbox, history import jobs.
- Additional models cover usage records, device tokens, canned responses,
  contact identities, and WhatsApp coexistence events.

`ProviderCredential` replaced `AIConnection`; migration `0007` dropped
`ai_connections`. Do not recreate a connections API based on stale documentation.

Tenant isolation is enforced by application queries, not an audited RLS layer.
Filter agency resources by the authenticated user's agency; portal resources must
belong to the authenticated client. Preserve ownership checks through related
objects, background jobs, media access, and tools. Never trust a submitted tenant ID.

Agency login uses JWT HS256 in httpOnly cookies; passwords use bcrypt. Portal
sessions use a separate token type and cookie, also accepted as bearer tokens for
mobile. Mobile session persistence uses secure storage. Registration defaults to
one agency: the first registration closes public signup unless
`ALLOW_MULTI_AGENCY=true`. This switch does not implement SaaS billing or quotas.

`app/database.py` is the single session creation boundary. Routes depend on
`get_db`; background work calls `new_session()`. Never call `SessionLocal()`
outside that module. Tests and deployments depend on session substitution;
`tests/test_session_factory.py` enforces this convention.

## Directory map and important modules

| Path | Purpose |
| --- | --- |
| `apps/api/app/main.py` | FastAPI setup, CORS, router registration, background task lifecycle. |
| `apps/api/app/config.py` | Typed settings and environment loading. |
| `apps/api/app/models.py`, `schemas*.py` | Persistence models and request/response contracts. |
| `apps/api/app/security.py`, `deps.py`, `ratelimit.py` | Secrets, sessions, authentication dependencies, per-IP limits. |
| `apps/api/app/routers/` | Auth, agency, clients, agents/tools, providers/catalog, conversations, dashboard, portal/mobile, channels, widget and public callbacks. |
| `apps/api/app/services/ai.py`, `providers.py` | OpenAI Responses and Anthropic Messages calls; agency credentials. |
| `apps/api/app/services/knowledge.py`, `embeddings.py` | PDF-derived knowledge, Q&A context, semantic/keyword retrieval and prompts. |
| `apps/api/app/services/tools/` | HTTP/MCP execution, discovery, specifications and agent tool loop. |
| `apps/api/app/services/whatsapp*.py` | QR/Cloud delivery, inbound processing, identities, templates and coexistence. |
| `apps/api/app/services/social*.py` | Social OAuth, Graph calls, policies, durable event/outbox processing and history import. |
| `apps/api/app/services/conversation_state.py`, `routing.py`, `escalation.py` | Lifecycle, assignment and human handover. |
| `apps/api/app/services/attachments.py`, `media.py`, `audio.py`, `operator_media.py` | Stored media, vision/transcription and voice-note processing. |
| `apps/api/app/services/notifications.py`, `mobile_privacy.py` | Notification provider boundary and mobile privacy behavior. |
| `apps/api/migrations/` | Alembic schema history; new schema changes require new migrations. |
| `apps/api/tests/` | Backend behavior and integration tests using a separate database. |
| `apps/api/storage/` | Runtime storage; contents are ignored except `.gitkeep`. |
| `apps/web/app/` | Login, dashboard, clients/channel setup, agents, inbox, settings, playground, portal and widget pages. |
| `apps/web/components/` | Shared UI, shell, forms, media, tools, channel setup and reply policies. |
| `apps/web/lib/api.ts` | Shared fetch wrapper with cookie credentials and API origin. |
| `apps/web/lib/i18n/` | Typed English/Spanish UI dictionaries and language provider. |
| `apps/web/lib/providers.ts`, `agent-templates.ts` | Provider/model presets and agent starter content. |
| `apps/web/types/`, `public/widget.js`, `proxy.ts` | Web contracts, embed script and verified custom-domain routing. |
| `apps/whatsapp/` | Go server, backend client, session manager, message/cache logic and tests. |
| `apps/mobile/` | Expo app, screens/components, API/session/media/push code, brands, native plugins and tests. |
| `docker/`, `docker-compose.yml`, `Makefile` | Gateway, database initialization, service wiring and operational commands. |
| `scripts/generate-docker-env.sh` | Creates local Docker configuration with random secrets; refuses overwrite. |
| `docs/en/`, `docs/es/`, `README.md`, `CHANGELOG.md` | Guides and history; some content still describes older OpenLivery behavior. |
| `.github/workflows/publish-images.yml` | Builds and publishes service images on main/tags or manual dispatch. |
| `.githooks/` | Pre-commit guard. |

## Technology stack

Versions below were observed during the initial audit; manifests and lockfiles
remain authoritative for subsequent work.

- Web: Next.js 16.3, React 19.2, TypeScript, Tailwind 4/PostCSS, Lucide, ESLint 9.
  Next's installed package requires Node >=20.9; the web Dockerfile uses Node 22.18.
- API: Python 3.12 in Docker, FastAPI, Pydantic Settings, SQLAlchemy 2, Alembic,
  psycopg, HTTPX, PyJWT, bcrypt, cryptography/Fernet, pypdf and the MCP SDK.
- Database: PostgreSQL 17.6 in Compose. Knowledge embeddings are JSON and cosine
  ranking runs in Python; there is no vector database extension in this design.
- Bridge: Go 1.27 declared in `go.mod`, whatsmeow, PostgreSQL or SQLite session store.
- Mobile: Expo 57, React Native 0.86, React 19.2, TypeScript, SecureStore, native
  audio/media and notifications. It has its own package and lockfile.
- Infrastructure: Docker Compose, Caddy; FFmpeg in the API image for voice notes.

## Integration behavior to preserve

OpenAI and Anthropic resolve to fixed cloud URLs in `services/providers.py`.
Their low-level clients accept a URL, but this is not a user-configurable
arbitrary OpenAI-compatible provider feature. Ollama has a configurable native
endpoint through the same provider boundary; see the phase 2 section below.
Vision/transcription and embeddings use the OpenAI credential path. Knowledge
retrieval includes small document sets in full, uses semantic search for larger
sets when available, and falls back to keyword search.

QR inbound messages reach
`POST /api/internal/whatsapp/channels/{channel_id}/inbound`. Preserve bridge token
authentication. whatsmeow owns the actual session keys in its SQL store; the API
stores an encrypted restoration marker, not that entire store. Do not claim all
bridge data is encrypted by the API's `ENCRYPTION_KEY`.

WhatsApp reply delay is per agent, normally 6-9 seconds. A new message restarts
the quiet-window timer; zero bounds allow synchronous replies. Human mode pauses
AI responses. Social events and outbox rows are persisted and processed by the
social worker; do not assume QR/Cloud reply timers have the same durability.

Social connectors enforce signed callbacks, scoped identities and response
windows. Preserve deduplication, historical-message semantics and uncertain-send
handling. Automated mocks do not establish Meta approval or actual delivery.

Push defaults to `none`. The included `webhook` provider delegates delivery;
native APNs/FCM delivery needs matching application identity and provider setup.

## Running development

The user-facing local review URL is `http://localhost:3000`. Keep requested
changes available there using the existing Compose services; do not substitute
a separate preview port as the delivered UI. Isolated test environments remain
appropriate for automated verification. After checks, update only affected local
services and verify the routes on port 3000.

Inspect existing configuration and service ownership before starting anything.
Never start a stack against real customer data or overwrite a private env file.
Startup can apply migrations, restore channels, or process queued messages.
Use isolated development data and authorized integrations.

### Isolated agent verification

Prefer `make verify-api` and `make verify-web` for autonomous changes. See
`docs/en/local-verification.md` for setup, safeguards, explicit Webpack fallback,
and the local preview cycle (`make preview-api`, `make preview-web`). These use
`docker-compose.verify.yml`, a separate fixed `tkila-verify` project, temporary
PostgreSQL data and an internal network; never merge it with the main Compose file.
Only one agent may use this fixed project at a time. `make verify-api-stop` removes
only these disposable containers. Preview data is synthetic and temporary.

Starting Docker Desktop can automatically resume unrelated containers due to their
restart policies. Check this before starting a stopped daemon; do not resume real
customer integrations to run tests. On the inspected host `/usr/local/bin/node`
is v24.14.1 but the default NVM PATH selects v18.20.8. Select a supported Node
runtime explicitly; do not assume the default PATH is suitable for Next.js.

### Docker

Run from the repository root:

```bash
make help
make up
make ps
make logs SERVICE=api
```

`make up` generates `.env.docker` only if absent, builds and starts the stack.
The API container runs `alembic upgrade head` before starting Uvicorn. For an
explicit first-time configuration, `./scripts/generate-docker-env.sh` exists and
refuses to overwrite an existing file. Never print its private output file.

Default endpoints: app `http://localhost:3000`, API docs
`http://localhost:8000/docs`; bridge port 3101 is internal in Docker.
`API_PORT`, `WEB_PORT`, `DB_PORT`, and `BIND_HOST` control host bindings:

```bash
API_PORT=8001 WEB_PORT=3001 DB_PORT=5433 make up
```

`make migrate` applies migrations to the configured API database; it is not a
read-only check. `make pull` uses prebuilt OpenLivery images by default and does
not validate local Tkila Box edits. Do not run `make destroy`: it removes volumes.

### Local API and frontend

Use PostgreSQL and a Python 3.12 environment. Prepare a private development `.env`
from `.env.example` only if needed; set a separate development database and unique
secrets. API settings load the root `.env` and `apps/api/.env`. FFmpeg must be
available for operator voice-note conversion.

```bash
# From the repository root
cd apps/api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

In another terminal, with a supported Node version:

```bash
# From the repository root
cd apps/web
npm ci
NEXT_PUBLIC_API_URL=http://localhost:8000 BACKEND_INTERNAL_URL=http://localhost:8000 npm run dev
```

Next does not inherit the root API `.env` simply because both apps share a repo.
Pass the web variables explicitly or use its own local environment configuration.
There is no frontend `/api` rewrite in `next.config.ts`; standalone local web
needs the API origin. Docker's gateway instead supports the empty same-origin URL.
`NEXT_PUBLIC_API_URL` is baked into production builds.

### Optional bridge and mobile

With Go 1.27 and an isolated bridge store:

```bash
# From the repository root
cd apps/whatsapp
go run .
```

The bridge reads a nearby/root `.env`. Match `WHATSAPP_BRIDGE_TOKEN` with the API;
configure `BACKEND_URL`, `WHATSAPP_BRIDGE_URL` and optionally `WHATSAPP_STORE_URL`.
The default store is local SQLite; Compose uses a `whatsmeow` PostgreSQL schema.

Mobile development requires the platform SDK/emulator and a native development
build. Follow `apps/mobile/README.md` and `WHITELABEL.md`; do not assume Expo Go is
sufficient or publish the example identity.

```bash
# From the repository root
cd apps/mobile
npm ci
BRAND=example APP_VARIANT=development npx expo run:ios
# Alternative with an Android emulator:
BRAND=example APP_VARIANT=development npx expo run:android
# After the development build exists:
BRAND=example APP_VARIANT=development npx expo start --dev-client
```

The iOS simulator uses localhost; Android emulator uses `10.0.2.2` for the host.
Physical devices need a reachable development server. Native HTTP is allowed for
development variants; release variants require HTTPS. Never put real credentials
in `EXPO_PUBLIC_DEV_*` variables or invoke paid hosted builds without authorization.

## Configuration and conventions

- All code, identifiers, routes, comments, commit messages and repository docs
  must be English. End-user UI belongs in typed i18n keys, English default and
  Spanish supported. Preserve existing translated guides. Customer-language
  system prompts in `knowledge.py` are an intentional exception.
- Read `apps/web/AGENTS.md` and the relevant bundled Next documentation under
  `apps/web/node_modules/next/dist/docs/` before nontrivial Next changes. Next 16
  uses `proxy.ts`; do not introduce older middleware conventions blindly.
- Keep backend schemas, frontend types, mobile contracts and migrations aligned.
  Preserve human takeover, tenant ownership and playground isolation from the
  customer portal and its reports.
- Add a migration for schema changes; do not rewrite applied history casually.
- Keep `ENCRYPTION_KEY` stable once encrypted credentials exist. `SECRET_KEY`
  signs sessions; `COOKIE_SECURE`, `COOKIE_SAMESITE`, and `FRONTEND_URL` govern
  cookie/CORS behavior. Development defaults are not production hardening.
- `RATE_LIMIT_ENABLED` controls in-process IP limiting. Forwarded IP headers are
  only as trustworthy as the proxy chain; there is no shared limiter store.
- `TOOLS_ALLOW_PRIVATE_URLS` affects the HTTP tool guard; keep it disabled by
  default. Do not assume MCP shares that guard.
- `SOCIAL_*`, `INSTAGRAM_*`, `MESSENGER_*`, and `META_GRAPH_BASE_URL` settings are
  defined in `config.py` and documented examples/social guides. Read the exact
  definitions rather than inventing provider configuration.
- Caddy serves HTTP by default. Custom-domain HTTPS is opt-in using
  `docker/Caddyfile.ondemand`, verified `/api/public/portal-domain` resolution,
  `proxy.ts`, and `BACKEND_INTERNAL_URL`. There is no `make deploy` target.
- Enable the guard once per clone: `git config core.hooksPath .githooks`.
  It blocks local-only files and forbidden staged content. Do not quote its
  blocking markers in tracked documentation or bypass the guard casually.
- Internal notes and roadmaps belong in ignored `work/`; `internal/` and
  `*.local.md` are also local-only. Keep secrets and generated artifacts out of Git.

## Validation and completion criteria

Start and finish with `git status --short` and inspect the relevant diff. Record
existing failures before changing behavior. Select checks appropriate to the
change; documentation-only edits need content/link/diff checks, not a live stack.
Do not use a destructive test environment merely to satisfy a checklist.

### Web (run in apps/web)

```bash
npm run lint
node node_modules/typescript/bin/tsc --noEmit --incremental false
npm run build
```

The `npm run typecheck` script runs the same local compiler command.
`npm run verify` chains lint, typecheck and build; `npm run build:webpack` is an
explicit fallback for restricted environments where Turbopack cannot open ports.
There is no web unit-test suite or `test` script. UI changes should also
be checked in the browser when a safe local environment is available. A build can
write generated files and require external font downloads; report blocked checks.

### Backend (run in apps/api)

Only run the following after confirming an isolated, disposable test database.
`tests/conftest.py` requires an explicit `TEST_DATABASE_URL` and
`TKILA_TEST_ALLOW_RESET=1`, rejecting nonlocal hosts, databases without an `_test`
suffix and URL query overrides before application import. It disables dotenv
loading and inherited application settings and uses temporary attachment storage.
It calls `drop_all/create_all` per test. This drops test tables, not the database;
the name/host guard does not prove data is disposable. Prefer `make verify-api`,
which provisions the isolated target and prevents runtime Internet access.

```bash
pytest -q
pytest tests/test_flows.py::test_register_login_logout_and_me -v
alembic heads
alembic history
```

For schema changes, validate an upgrade in a disposable database as well: the
pytest fixture creates tables from models and does not prove migrations work.
Never run a downgrade on valuable data. Migration `0007` drops legacy connections
without transferring their credentials; account for that when assessing old installs.

### Bridge (run in apps/whatsapp)

```bash
go test ./...
go vet ./...
```

### Mobile (run in apps/mobile)

```bash
npm run typecheck
npm test
npm run test:native-contracts
npm run test:api
```

The API module tests use mocks. `npm run verify-flow` is different: it targets a
running server, changes conversation state and sends a reply. Use it only with
explicitly authorized disposable accounts/channels. Native device checks and real
push delivery must be reported separately from mocked tests and type checking.

### Docker checks and CI limits

`docker compose --env-file .env.docker exec api pytest -q` and `make test` exist,
but are legacy commands for the main stack; the new fixture guard intentionally
rejects their default `db` host and absent reset consent. Do not weaken the guard
to use an existing stack; use `make verify-api` instead. `make test` runs
backend pytest and builds web/bridge images. The web Dockerfile runs lint/build;
the bridge Dockerfile runs vet/tests/build. The API Dockerfile installs tests but
does not run them. The audited image-publishing workflow is not a pull-request
validation pipeline. Do not push to trigger publication as a verification shortcut.

Never interpret passing mocks, syntax checks or type checks as proof of live AI,
Meta delivery, push delivery, production readiness, or migration correctness.

## Audit baseline and current product gaps

The initial audit found implemented agency/client/agent management, knowledge,
HTTP/MCP tools, playground, inbox, portal, teams, contacts, reports, five channel
families, and a mobile inbox. These are real implementations, but full runtime
and external-account acceptance were not executed during that audit.

Known gaps and legacy areas to recheck before related work:

- Login dashboard numbers and automation rows are static demonstrations. There
  is no Google Calendar module. Native appointments now have a local `/appointments` implementation;
  see `docs/en/appointments.md` for capacity and integration limits. The dashboard preview
  rows are separate from the native `/automations` module.
- Sidebar Integrations and Reports entries have no routes;
  dashboard and portal reports do exist elsewhere. Automations now has a native
  `/automations` module; see `docs/en/automations.md`.
- Google/Apple login and password recovery buttons are disabled. Remember-me is
  not wired to session behavior. Login forces Spanish; dashboard formatting also
  contains fixed Spanish locales.
- No commercial subscription, payment, plan-quota or SaaS billing implementation
  was found. Extension hooks and usage records are not a billing system.
- README, package/container/image names, API title, Go module and DNS challenge
  still contain OpenLivery identity. The Tkila Box shell still uses its old logo;
  mobile remains a generic example brand. Do not blindly rename persistent IDs.
- README marks Instagram/Messenger as planned despite implementation. Older
  architecture text describes removed AI connections and arbitrary provider URLs.
  Some comments still name the former Baileys bridge. Social documentation exists
  in English without a matching Spanish guide at audit time.
- MCP discovery/calls do not apply the HTTP private-address guard. HTTP protection
  itself documents a DNS-rebinding limitation. Treat this as a SaaS security priority.
- `_public_client` checks client activity, while `_portal_client` does not recheck
  `Client.is_active` for existing sessions. Review deactivation semantics and tests.
- WhatsApp deferred replies use process-local tasks; restarts lose timers and
  multiple workers need concurrency review. Social persisted queues differ.
- Dashboard agent totals include soft-deleted agents and channel totals omit
  widgets. Web dashboard errors are swallowed; a fetched conversation state is
  written but no longer consumed.
- Portal lint reported unused imports, state and functions including bulk archive,
  deletion and contact-block handlers. Community/Discord helper files had no web
  references found. Verify reachability before removing any of this code.
- Large portal/model/schema/CSS files, Python-side vector ranking, polling and
  in-memory rate limits warrant targeted maintenance and capacity measurements.
- No explicit TODO/FIXME/NotImplemented markers were found in the searched app
  code; absence of markers is not evidence of feature completeness.

Audit verification: web TypeScript passed; lint had 0 errors and 11 portal
warnings; 148 Python files parsed; 37 migrations had one root and head
`0038_whatsapp_coexistence` with no missing parents (`0032` intentionally follows
`0030`). There were 264 backend test functions, not executed in that session.
The host then had Node 18, no Go in PATH and no required Python packages; recheck
current tooling rather than treating those machine details as permanent facts.

The initial Git baseline was `main` at `d18e5da`, with 17 modified web files and
six untracked web files covering branding/login, dictionaries, styles and PostCSS.
These were existing user changes. They are not a clean baseline to reset to;
inspect the current tree every time. No private env contents or live database
migration state were verified by the audit.

## Current technical priorities

1. Preserve and review the existing Tkila Box changes in small, scoped diffs.
2. Establish reproducible, disposable development/test environments; guard test
   targets and add meaningful pull-request and migration validation.
3. Address MCP network access, portal deactivation and WhatsApp timer durability
   with focused regression coverage before scaling the SaaS.
4. Align branding, docs, configuration, dashboard accuracy and visible feature
   promises with actual behavior; avoid broad compatibility-breaking renames.
5. Agree on the first complete Tkila Box business flow before building missing
   appointments or commercial SaaS modules. Reuse the verified core and the
   native automation module documented below.

These priorities guide related work; they do not authorize unrelated refactors,
production changes, live integrations, spending, or implementation beyond the task.

## Native automations

Migration `0039_native_automations` adds definitions, run history and scheduled
actions. `services/automations/` validates events, evaluates a closed condition
DSL and runs a PostgreSQL queue inside the API lifespan. Message capture is
transactional and excludes playground, historical and automation-generated
messages. Client creation emits directly. The worker uses row locks, immutable
run snapshots, bounded connection retries and conservative uncertain-send
handling; do not replace it with in-memory delay timers.

HTTP headers are encrypted and masked on reads. The shared HTTP URL guard has
an explicit strict mode for automations that cannot use the development private
URL bypass. `AUTOMATION_WORKER_ENABLED=false` disables processing for isolated
tests. See `docs/en/automations.md` for available triggers/actions, cancellation,
channel policy and recovery semantics. Native appointments extend this queue with appointment lifecycle events and
revision-checked upcoming reminders; see `docs/en/appointments.md`. CRM-stage
integration remains absent.


## Appointment calendar integration

Migration `0041_appointment_calendars` adds per-client encrypted Google OAuth
connections and durable sync fields on appointments. `services/google_calendar.py`
provides free/busy and event operations; `services/calendar_worker.py` retries
pending sync under the shared client lock. OAuth routes are in
`routers/appointment_calendars.py`. Never serialize connection/token ORM rows.
Normal availability fails closed on connected-provider failures. Google event
updates/deletes require private appointment/client ownership markers. Calendar
mappings remain pinned across disconnect/reconnect. Shared appointment services
and native AI tools use the same availability/queue path. See
`docs/en/appointments.md` for environment variables, callback, outbound-only sync,
retry semantics and reminder preferences (which do not send messages themselves).


## Automation template experience

`/automations` defaults to contextual recommendations with cross-category multi-selection
and shared simple configuration blocks; My automations and the existing advanced
builder remain available. The reusable
web registry generates the existing DSL. Migration `0042_automation_templates`
adds nullable origin metadata only; legacy rules remain Custom and worker semantics
are unchanged. Simple editing requires a lossless supported rule shape, otherwise
use the advanced builder. New-contact, conversation-start and out-of-hours cards
are unavailable. Appointment messages use linked conversations; inactivity includes
activity from either side. See `docs/en/automations.md` for precise template limits.

## Agent-centered configuration foundation (phase 1)

Migration `0043_agent_configuration` adds `Agent.objectives` (default empty list)
and nullable `template_id`. Existing instructions and permissions remain effective;
these fields do not automatically provision channels, tools or automations.
`services/agent_catalog/` and the authenticated `/api/catalog/agent-configuration`
endpoint define objectives and industry presets for the future builder. The old
wizard remains unchanged. `services/model_providers.py` wraps the existing OpenAI
and Anthropic transports; other catalog providers are not implemented adapters.
`tools/registry.py` loads the existing enabled per-agent allowlist with explicit
agency/client checks. Knowledge remains injected context, native appointment
permissions remain bundled, and streaming/Ollama were not implemented in phase 1; phase 2 adds Ollama below.
See `docs/en/agent-architecture.md` for the mapping, limits and phase boundaries.


## Ollama provider (phase 2)

Migration `0044_ollama_provider` extends `ProviderCredential` with nullable name,
base URL and default model; one provider connection per agency remains enforced.
`services/ollama.py` implements the existing ModelProvider boundary with native
`/api/tags`, `/api/show` and non-streaming `/api/chat`. Agents keep provider/model;
connection ownership is resolved by agency, never by a submitted tenant ID.
`/providers` configuration/test/validate routes are reused; model refresh,
capabilities and a non-persisted inference probe are available under that router.
The web Settings and legacy agent forms support dynamic installed model selection.
Unknown tool support fails closed. Allowed calls use ToolRegistry and the existing
executor; inbound media preprocessing still uses OpenAI. Optional proxy bearer
keys use the existing encrypted key field and never appear in responses.
`OLLAMA_BASE_URL` supplies the installation default (stored connection wins),
`OLLAMA_TIMEOUT_SECONDS` bounds generation, and `OLLAMA_ALLOWED_PRIVATE_ORIGINS`
is an exact deployment-controlled private origin allowlist. Other origins use the
strict shared HTTP SSRF guard, with its documented DNS-rebinding limitation.
Do not use the HTTP tools development bypass for Ollama. No model is downloaded
or pulled by Tkila Box. See `docs/en/ollama.md` for Mac/Docker setup and limitations.

## Visual agent builder (phase 3)

`/agents/new` now offers eight guided steps and retains the advanced form.
Migration `0045_agent_builder` extends the existing Agent with channel preferences,
shared tool references, tone, welcome guidance and a knowledge permission. The
existing create/update API validates guided provider/model choices. The scoped
`/api/catalog/agent-configuration/{client_id}` reports tool/calendar readiness.
Shared tools are explicit references restricted to the same agency and client;
runtime resolution rechecks enabled/deleted state. Channel preferences do not
reassign live channels. Automation suggestions reuse the existing templates and
require separate activation; existing definitions are preserved. Agent detail
uses the existing playground, knowledge and advanced tools pages. See
`docs/en/agent-builder.md` for limits and the optional isolated Ollama preview.

## Groq cloud provider

Groq is registered in the existing ModelProvider boundary and uses the official
fixed cloud endpoint with Chat Completions. It reuses the agency-scoped encrypted
ProviderCredential and existing Agent provider/model fields; the unique connection
is resolved by agency rather than a submitted connection ID. Saved credentials
precede the optional backend-only GROQ_API_KEY fallback. Models are discovered
from Groq, never from a static frontend list. Settings provides connection testing,
refresh and an explicit selected-model OK probe. The models API does not advertise
per-model tool/vision capabilities; a small inference probe confirms local function
calling without executing tools, cached for five minutes per key/model. This
consumes provider usage. Unknown tool support fails closed. Streaming
and structured output are not implemented. No migration is needed.

## Shared tool runtime (phase 4)

The existing `services/tools/runner.py` supplies native knowledge, appointment and
handoff tools plus the enabled agent/shared HTTP and MCP allowlist. Every provider
normalizes requests through `ToolDispatcher` and `ToolExecutor`; providers contain
no business execution logic. Ownership, active state, current grants, current tool
configuration and JSON Schema inputs are rechecked before execution. Remote schema
references are disabled. Native grants preserve the existing knowledge, appointment
bundle and escalation configuration; objectives remain suggestions only.

Migration `0046_tool_executions` adds durable execution records before side effects,
with scoped IDs, provider/model/channel, status, redacted arguments, safe result
summaries and latency. A provider failure does not erase successful actions. A
`started` record without completion is uncertain: inspect domain state before
retrying. Calls are capped at five total per turn, including denied calls. Unknown
Groq/Ollama tool support falls back to chat with warnings; legacy unknown cloud
model IDs retain their existing transport compatibility. Tool-capable models use
the same executors. Playground remains isolated from real appointments and handoff.

Runtime HTTP and MCP calls use strict destination validation, without the HTTP
development private-URL bypass. HTTP tools reuse their configured, encrypted
headers and fixed destinations; URLs/headers are not model-controlled. The shared
DNS-rebinding limitation remains. Knowledge search is limited to the current
agent's documents and Q&A. Appointment tools call the existing service and durable
Google sync queue; a committed booking is not a claim of completed external sync.
Handoff can now wait unassigned when the business has no team. Social delivery
continues to apply its existing deferred handoff policy. The agency-scoped
`GET /api/conversations/{id}/tool-executions` supports optional Playground activity.

## Industry agent templates (phase 5)

The backend `agent_catalog/templates.py` now supplies 46 versioned bilingual
starters and explainable recommendations through the scoped catalog router.
The existing Builder applies editable previews; `/agents/templates` adds a
searchable library and the dashboard recommends starters for businesses without
agents. Migration `0047_agent_template_snapshots` adds nullable origin version and
snapshot to the existing Agent; it does not backfill or overwrite legacy settings.
Normal edits never reapply live defaults. Explicit template changes require UI
confirmation. Native calendar permissions require configured services/hours;
external tools and suggested automations need separate explicit configuration or
activation. Required business information is an advisory checklist, not document
completeness detection. See `docs/en/agent-templates.md` for API, scoring and limits.

## Multi-select automation configuration

`/automations` defaults to contextual Recommended with All, My automations and
Advanced tabs. Available cards are selectable across categories; the shared simple
fields configure selected blocks before explicit summary confirmation. Batch save
uses `POST /api/automations/batch` to create separate records atomically for one
owned business, with stable IDs for safe identical retries. Recommendations reuse
phase-five matching and current agent objectives through the scoped automations
router. No migration or worker change is required. Linked-channel behavior,
keyword-only handoff, static webhook payloads, unavailable templates and lossless
advanced editing restrictions remain effective. See `docs/en/automations.md`.


## Functional objectives and industry templates

The phase-five catalog contains 46 bilingual versioned templates across ten business
types plus six general starters. Migration `0047_agent_template_snapshots` pins
origin metadata while copied settings remain editable. Migration
`0048_managed_objectives` adds objective settings and stable managed-rule ownership
to the existing models. Saving explicit objectives synchronizes only their managed
rules through the existing automation engine; legacy/manual rules remain custom.
The normal builder configures objectives, while custom flows remain under Agent >
Advanced. Do not restore a separate automation activation step for managed agents.
See `docs/en/agent-templates.md` and `docs/en/objectives.md` for exact limits.
