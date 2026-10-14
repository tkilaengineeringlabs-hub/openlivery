# Agent-centered architecture — phase 1

## Existing model and boundaries

The existing architecture already follows Agency -> Client -> Agent. This phase
adds configuration contracts without replacing the runtime or creation screens.
`client_id` remains the business identifier; no second Business table is introduced.

| Concern | Existing source of truth | Phase-one treatment |
| --- | --- | --- |
| Workspace and authentication | `Agency`, `User`, `deps.py`, cookie JWT; separate portal/mobile sessions | Unchanged |
| Business identity | `Client.name`, `industry`, `business_type`, `business_custom`, timezone and appointment settings | Reused; no copied business entity |
| Agent | `Agent.client_id`, `agency_id`, `name`, `instructions`, `personality`, `provider`, `model`, `is_active`, timestamps | Reused |
| Description and business brief | `Agent.brief_summary/products/audience/policies/dos/donts` | Preserved; these are agent-owned today, not shared Client context |
| Channels | WhatsApp QR/Cloud, Widget and Social channel rows hold `client_id` and `agent_id` | Reused; no agent JSON copy of channels |
| Provider credentials | Encrypted `ProviderCredential` keyed by agency/provider | Unchanged; never part of catalog metadata |
| Knowledge | `KnowledgeDocument`, `KnowledgeChunk`, `AgentQA`; `retrieve_knowledge` and `build_system_prompt` | Reused; retrieval is context injection, not a callable `knowledge.search` tool yet |
| Custom tools | `AgentTool`, enabled per agent, encrypted headers, HTTP and MCP | Existing enabled rows remain the allowlist |
| Native appointment tools | `appointments_enabled`, `tools/appointments.py`, verified conversation and tenant checks | Existing permission bundle retained |
| Handoff | Escalation destinations, built-in toggle, `EscalationRule`, `escalate_to_human` | Existing rules and deferred handoff retained |
| Appointments/calendar | `Appointment`, services/availability, client-scoped encrypted Google connection and durable sync | Reused; no generic new calendar integration or credential store |
| Automations | Definition/run/action tables, client/agency scope, existing queue | Separate deterministic engine; templates only recommend activation |

Agent CRUD validates ownership through `_agent` and `_validate_client`. Tool CRUD
resolves the owned agent before its tools. Calendar operations resolve the client
and agency. Native appointment handlers recheck agent, conversation, customer scope
and business inside their execution transaction. Tenant isolation is application
query logic, not an audited RLS layer.

The WhatsApp QR bridge is Go/whatsmeow, not Evolution. A separately running
Evolution container does not establish an application integration. Instagram,
Messenger, QR/Cloud WhatsApp and Webchat are implemented channels. Telegram,
Mercado Libre and Amazon are not registered as working channels or tools.
Google Calendar is a client-level appointment integration. Apple/iCloud, Gmail,
Sheets and marketplace adapters remain unimplemented.

## Runtime and provider boundary

The conversation/playground route, widget route and WhatsApp/social inbound paths
reuse credential resolution, knowledge retrieval, `build_system_prompt`, and
`tools.runner.run_completion`. The runner loads enabled custom tools, contextual
appointment tools and trusted escalation specs, invokes the selected provider,
and returns the existing `Completion`. Caller-specific message persistence,
usage reporting, channel policy, human takeover and delivery remain in place.

`services/model_providers.py` exposes the `ModelProvider` protocol, provider
registry, `ModelCapabilities`, `OpenAIProvider` and `AnthropicProvider`. Adapters
delegate to existing `ai.py` transports and tool loops; no request format or
sampling retry is rewritten. Tool schemas remain provider-neutral `ToolSpec`
objects, adapted by the existing loops. Streaming explicitly raises unsupported;
it is not emulated by returning a buffered reply. Unknown model capabilities are
`None`, rather than inferred from a provider name. Vision metadata comes from the
existing catalog; actual inbound media preprocessing still uses the existing
OpenAI credential path.

Phase 2 adds Ollama alongside the OpenAI and Anthropic runtime adapters. The older model
catalog also lists other providers; catalog presence is not executable support.
The new agent-configuration catalog reports only registered providers. Existing
model/catalog endpoints remain compatible. Ollama connection/discovery/chat now uses this same boundary; see [Ollama](ollama.md).
Gemini has no runtime implementation.

`tools/registry.py` introduces `ToolRegistry` over existing specs and a loader
that rechecks agent/agency/client ownership, excludes disabled or unassigned tools
and rejects duplicate names. The existing loops refuse calls absent from their
provided specs. This is not yet a generalized integration-aware executor or a
per-native-tool permission model. HTTP/MCP permissions still derive from enabled
rows; native appointments remain a bundle and escalation retains its configuration.
The known MCP network-address guard gap and mid-loop permission-revocation review
are not solved by a configuration catalog.

## Configuration catalogs and persistence

`services/agent_catalog/` provides immutable bilingual objective, capability and
industry/objective template definitions. `GET /api/catalog/agent-configuration`
is authenticated and returns static, secret-free metadata for a future builder:
objectives, six industry presets, real capability descriptors, implemented channel
codes and registered providers. It does not describe tenant connection status.
Recommendations never grant permissions or activate integrations/automations.
Order and inventory objectives require an explicitly configured external tool;
there is no built-in marketplace lookup. Knowledge is marked `context`, HTTP/MCP
are `custom_tool`, and appointment/handoff capabilities are `native_tool`.

Migration `0043_agent_configuration` adds only:

- `agents.objectives`: JSON, non-null, database default `[]`.
- `agents.template_id`: nullable string, no backfill.

Existing agents keep empty objectives and no template. CRUD accepts validated
objective IDs and optional known template IDs. Omitted PATCH fields preserve
saved values; `[]` clears objectives and `null` clears template origin. These are
metadata during phase 1: saving them does not rewrite instructions or enable tools.
`template_defaults` explicitly produces ordinary AgentCreate fields for an opt-in
caller; it does not persist anything itself. The downgrade removes only the two
new fields and should be used only under the environment's normal data procedure.

The current five-step web wizard, central frontend starter presets
(`lib/agent-templates.ts`), list and four-tab detail screen are unchanged. The new
catalog is the source for the future seven-step builder; legacy frontend presets
must be reconciled during phase 3, not silently replaced in this phase. Web agent
types accept optional metadata for compatibility with older API responses. The
mobile API uses portal contracts rather than this agency AgentCreate contract.

## Next phases

2. Ollama transport, connection discovery and model/tool capability checks are implemented;
   live Mac/Docker acceptance remains a deployment check. See [Ollama](ollama.md).
3. Consume the configuration catalog in the new wizard and agent detail; use real
   client channel/connection states. Apply defaults only with an explicit selection.
4. Extend the existing prompt builder with objectives and implement explicit native
   permissions and an integration-aware execution context. Move shared business
   context only with a separate compatibility and ownership migration plan.
5. Add declarative integration surfaces for future marketplaces, marked unavailable
   until actual authorization and backend adapters exist.

## Verification

Use the isolated test project, never the application database:

```bash
bash scripts/verify-api.sh -q tests/test_agent_architecture.py tests/test_agent_tools.py tests/test_flows.py tests/test_appointments.py tests/test_google_calendar.py tests/test_session_factory.py
```

The tests mock network/model effects. They do not prove live provider delivery.
Fresh migration verification uses `make preview-api` and `alembic current` inside
the disposable preview, per `local-verification.md`. Phase 1 does not change the
visible UI and does not deploy the existing instance at localhost:3000.

### Phase-one result (2026-10-01)

- 58 primary backend regression cases passed; 12 final registry/Google Calendar
  cases passed (70 total). Provider and integration effects were mocked.
- Existing Starlette/AnyIO deprecation warning remains.
- Web TypeScript, full lint and production Webpack build passed. Lint retains the
  11 pre-existing portal warnings and reports no errors.
- The isolated preview upgraded from `0042_automation_templates` to
  `0043_agent_configuration`; Alembic reported the expected head and the API became
  healthy. The main application containers were not rebuilt or migrated.
- `git diff --check` passed. The current agent wizard and detail UI are unchanged.
- Phase 2 was not started. No live AI call or new provider connection was tested.
