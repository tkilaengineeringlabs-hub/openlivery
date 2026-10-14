# Native automations

Automations are managed at `/automations` by authenticated agency users. They use
FastAPI, PostgreSQL and the existing web UI. No additional execution service is
required. Apply migration `0039_native_automations` before starting the updated API.
Do not run migrations against a valuable environment without its normal rollout
and backup procedure. The migration adds three tables and does not rewrite data.

## Rules and scope

A rule has an optional business scope, an event, AND conditions and ordered actions.
The API validates the complete rule on create and partial update. Unknown action
kinds, condition fields, operators and configuration keys are rejected. At most
20 conditions and 20 actions are allowed; a delay is bounded to 30 days.

Available triggers:

- `message_received`: a newly persisted customer message on an existing channel.
- `client_created`: the real business creation endpoint. This has no conversation
  destination, so only delay and HTTP actions are allowed.
- `conversation_inactive`: a message from either side schedules a check for 5, 15,
  30, 60, 120, 360, 720, 1440 or 2880 minutes later. The check compares the source
  message with the latest exchanged message. More recent activity skips that run.
  New activity schedules a new check; there is no conversation-wide polling scan.

The shared SQLAlchemy message capture runs before commit, after IDs are assigned,
and calls `emit_event` directly. Runs and initial jobs commit with their source
message. Savepoints isolate rule evaluation errors. Historical messages, activity
records, playground messages and automation output cannot initiate automations.
This covers QR, Cloud, social and widget writers without parallel inbound APIs.
The client creation route emits its event directly in the same transaction.

Conditions read a closed JSON field set: `message.text`, `channel`, `client.name`,
`client.industry`, `conversation.mode`. Operators are `equals`, `not_equals`,
`contains`, `not_contains`, `exists`, `not_exists`. Equality is exact; contains is
case-insensitive. No expressions, templates, Python properties or executable
user code are evaluated. Event values are snapshots, rebuilt from owned rows.

Available actions:

- `send_message`: uses `send_channel_message` for WhatsApp and the widget's stored
  messages. Instagram/Messenger use the existing durable social outbox and policy
  checks. Human-controlled conversations skip automated sends. Cloud free-text
  messages require an open 24-hour inbound window. Social success means queued;
  final provider delivery remains visible in the inbox, not the automation status.
- `handoff_to_human`: uses the existing `set_mode` service and activity trail.
- `http_request`: GET, POST, PUT or PATCH, with headers, query parameters and a JSON
  object body. No response body is persisted. No redirects or environment proxies.
- `delay`: minutes, hours or days, persisted as the next due job rather than a
  sleeping request or an in-memory timer.

Actions are asynchronous after source commit. A handoff can therefore occur after
an AI response has already started; this module does not cancel in-flight AI work.
Appointment lifecycle and upcoming events use the same queue; see `appointments.md`.
CRM-stage events remain unsupported.

## Persistence and concurrency

`Automation` contains the rule, tenant and revision. `AutomationRun` contains a
minimal event snapshot, immutable action snapshot, status, counts, timestamps and
a safe error code. `ScheduledAutomationAction` holds one step with its due time,
attempt count, lease and status. Event uniqueness prevents duplicate runs for the
same rule/source event; run/action uniqueness prevents duplicate steps.

The API lifespan starts a lightweight worker unless
`AUTOMATION_WORKER_ENABLED=false`. Tests disable it and process jobs explicitly.
The worker checks due jobs every two seconds using an indexed query and
`FOR UPDATE SKIP LOCKED`. It commits a running marker before an external effect,
then holds the job lock during bounded execution. Each completed action and the
next scheduled step commit together. Definitions and referenced objects are
rechecked against the claimed agency and active business before each step.

Connection establishment failures retry up to three attempts, with 30/60-second
backoff. Read/write failures, provider errors and timeouts are not automatically
resent because the destination may already have accepted a request. After a crash,
expired internal jobs resume; expired external jobs fail as `delivery_uncertain`.
Check the destination before manually creating another run. Arbitrary HTTP/WhatsApp
providers cannot guarantee exactly-once delivery across process failure.

Disabling or editing a rule cancels pending jobs and preserves history. Already
in-flight effects may finish. Deletion removes the rule, history and queued jobs.
The history API paginates using `limit`/`offset`, returns counts and duration, and
never returns event text, stored headers or raw provider exceptions.

## Security

CRUD, run history, business selection and execution lookups are agency-scoped.
Only the trusted queue dispatcher scans jobs across agencies to obtain their tenant
context. All HTTP headers are encrypted using the existing stable encryption key;
API reads return masks, and unchanged masks preserve saved values by action ID.
Credentials belong in headers, not URL/query/body fields, which are ordinary rule
configuration. Error codes never include raw external errors or response content.

HTTP URLs reuse the existing Custom Tools private-address guard, including a
strict mode that ignores the development private-URL bypass. Validation occurs on
save and again at execution. The inherited DNS-rebinding limitation documented in
that guard still applies; redirects and proxy inheritance are disabled.

## Local verification

Run `bash scripts/verify-api.sh -q tests/test_automations.py` for disposable
PostgreSQL tests with mocked network effects. The suite covers rule validation,
tenant isolation, real persistence events, DSL outcomes, delay ordering, inactivity
cancellation, handoff, URL rejection, header encryption, disabled rules, recovery,
connection retries and transaction rollback. Existing widget/WhatsApp and session
factory tests provide regression coverage. See `local-verification.md` for the
separate migration/preview cycle and the documented Webpack fallback.

## Verification result (2026-09-23)

- Fresh disposable PostgreSQL upgrade through `0039_native_automations`: passed.
- Initial automation suite plus widget, WhatsApp and session-factory regressions:
  22 passed. Final worker/concurrency/integration revalidation: 11 passed,
  12 deselected. This covers 26 distinct cases across 33 executions.
- Both runs reported the existing Starlette/AnyIO deprecation warning.
- Web TypeScript and production Webpack build passed, including `/automations`.
- Full web lint passed with the 11 existing portal warnings; targeted automation
  lint passed without warnings. All 121 EN/ES translation paths matched.
- Default Turbopack build was blocked by the sandbox's internal-port restriction;
  the documented explicit Webpack fallback succeeded.
- No connected browser was available, so visual/responsive browser acceptance was
  not completed. External AI, WhatsApp and Meta delivery were not exercised.
  Network effects in the backend tests were mocked on the isolated test network.


## Multi-select recommended automations

`/automations` opens Recommended, with All, My automations and Advanced mode tabs.
Choose a business for recommendations derived from the existing phase-five matching
service, current agent objectives and pinned template suggestions. Cards are not
preselected or activated. Selection spans categories and tabs; a sticky counter
opens only selected blocks, followed by a review before activation.

The individual editor and batch stepper share the same fields. The batch creates
one independent record per selected block, including any deliberately paused
blocks. `POST /api/automations/batch` requires one owned business and supported
template references, validates all configurations in one transaction, and reuses
the existing header encryption, URL guard and reminder seeding. Stable UUIDs make
identical retries safe; changed retries return 409 rather than overwrite records.
`GET /api/automations/recommendations?client_id=...` is scoped to the agency.
No migration or execution-engine change is needed.

 My automations lists persisted rules,
business scope, optional template origin, enabled/paused state and the actual latest
run. Advanced mode retains the existing event/condition/action builder and history.
No execution count or draft state is synthesized.

The reusable web registry in `apps/web/app/automations/templates.ts` creates the
same `AutomationWrite` rule structure. Templates include appointment confirmation,
24-hour and 2-hour reminders, completed-appointment follow-up, inactivity follow-up,
lead recovery, keyword handoff, webhook and external event notification.
New lead, welcome and out-of-hours cards are explicitly unavailable because their
required events/conditions do not exist. Business creation is not contact creation.

Appointment messages support the existing variables and require a linked
conversation. Reminders cover scheduled and confirmed appointments; completed
follow-up requires marking the appointment completed, not merely reaching its end
time. Inactivity counts messages from either side; it does not infer an unanswered
lead or provide a maximum-attempt counter. Messages always use the existing
conversation channel; templates cannot choose an unrelated destination. Handoff
changes conversation mode without selecting an operator or team. Webhook data is
configured static JSON, not interpolated event data. Saved headers retain the
existing encryption and masked-update behavior.

Migration `0042_automation_templates` adds nullable `template_id` with no backfill
or change to execution. Older rules appear as Custom. Origin is advisory UI metadata;
it is never used for ownership or worker decisions. Unknown origins remain editable
in advanced mode. Simple creation requires an agency-owned business. The existing
API continues to support agency-wide rules and validates ownership as before.

Simple editing is available only when the full rule can be represented without
loss. Additional advanced actions, conditions or a changed trigger open in advanced
mode. Switching from the simple form transfers unsaved values, including HTTP header
masks and action IDs. Saving uses the same POST/PATCH API and pending-run cancellation.
There is no parallel engine or browser timer.

### Template verification (2026-10-01)

- Disposable PostgreSQL: 38 automation, appointment and session-factory tests passed,
  including nullable origin round trips and template rule persistence. Network
  effects were mocked. The existing Starlette/AnyIO deprecation warning remains.
- Fresh preview migration upgrade through `0042_automation_templates` passed;
  `alembic current` reported that single head. Preview services were stopped after
  verification. No production migrations were applied.
- Web TypeScript and production Webpack build passed. Full lint had no errors and
  the same 11 pre-existing portal warnings; automation-specific lint was clean.
- Three template contract tests passed: supported rule round trips, safe advanced
  fallback and rejection of unavailable catalog entries. To run from `apps/web`,
  compile `app/automations/templates.test.ts` with the local TypeScript compiler
  using `--outDir /tmp/tkila-template-tests --module commonjs --target es2022
  --esModuleInterop --skipLibCheck`, then run `node --test
  /tmp/tkila-template-tests/app/automations/templates.test.js` with Node >=20.9.
- No browser was connected to the available UI tool. Visual/responsive acceptance
  remains pending, as does real provider delivery; neither is implied by these tests.
