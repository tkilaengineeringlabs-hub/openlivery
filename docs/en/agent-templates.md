# Industry and objective agent templates

The existing backend registry in `app/services/agent_catalog/templates.py` defines
46 bilingual starters: four each for veterinary, dental, restaurant, ecommerce,
real estate, automotive workshop, beauty, clinic, agency and professional services,
plus six general starters. Industry and business-type codes reuse `app.industries`.
The old six template IDs remain valid. Objectives and capability IDs reuse their
existing catalogs; templates do not add executable tools.

## Recommendations and application

`POST /api/catalog/agent-templates/{client_id}/recommendations` accepts objectives
and planned channels. Ownership, connected channels and available capabilities
are resolved by the backend. The score is the sum of industry (100), exact business
kind (80), shared objectives (15 each), available tools (2 each), and compatible
connected/planned channels (1 each). Scores and contributions are returned for
inspection. Ties retain registry order. General starters are recommended when no
exact business starter exists; the library and scratch option remain available.

`GET /api/catalog/agent-templates/{client_id}/{template_id}/preview?language=es`
returns safe starter defaults, unavailable tools, retired-reference warnings,
advisory business-information fields and a snapshot. It does not create anything.
The checklist describes information to add to the existing brief/Knowledge editor;
only native appointment services/hours are automatically detected as complete.
It is not a semantic audit of documents or a new client business-profile module.

The builder explicitly applies preview settings locally, which can then be edited
before the existing agent create API saves them. The API also supports explicit
`apply_template: true` on create/update; submitted custom fields override starter
defaults. The edit screen asks for confirmation before replacing configuration.
Migration `0047_agent_template_snapshots` adds nullable version/snapshot metadata
on the existing Agent. Legacy rows are untouched. Saved instructions, grants and
channel preferences remain independent of subsequent registry edits. Normal PATCH
requests do not reapply templates. Clearing template origin does not erase edits.

Managed objective grants are granular and are applied only when native services and
working hours are configured. Google Calendar is optional and must be connected
separately. External HTTP/MCP tools are never assigned by template inference;
native order and inventory objectives remain unavailable. Handoff uses existing rules and
permissions. Runtime prompt composition adds business context, objectives, tone,
custom instructions and actual permitted tools; no alternate runtime exists.

## UI and automation consent

`/agents/templates` provides search, category, industry and objective filters,
with optional scoped business ranking. Links lead to the existing builder and
preview. New-business creation retains its existing builder redirect. Businesses
without agents receive dashboard recommendations.

Templates now preconfigure objectives and their settings. Reviewing and saving an
agent is the activation boundary: managed follow-up and appointment rules are
synchronized by the existing automation engine. Previewing or selecting a card
alone has no server-side effect. Connections and channel assignments are never
created by template selection. Existing custom rules are preserved; technical
users can access Custom flows from the agent's Advanced tab.

See [objectives.md](objectives.md) for permissions, legacy behavior, scheduling,
and channel limitations.

## Verification

`tests/test_agent_templates.py` covers matching, registry references, scoped
preview, missing integrations, explicit apply, custom edits, pinned snapshots,
legacy/null origin, ready calendar grants, retired references and tenant isolation.
Use the isolated API verifier. Mocked provider tests do not establish live Groq or
Ollama acceptance; that acceptance remains separate.
