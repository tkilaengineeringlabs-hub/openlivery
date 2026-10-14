# Shared agent runtime and tools

The existing runtime in `services/tools/runner.py` resolves the agency/client/agent
and uses the same ModelProvider adapters. Each provider translates messages and
function calls; `ToolDispatcher` sends normalized requests to `ToolExecutor`.
There is no second agent engine. Explicit grants are the existing agent flags,
selected tools and enabled owned/shared AgentTool rows. Objectives recommend tools
but never grant permissions.

Native tools are `knowledge_search`, `check_appointment_availability`,
`create_appointment`, `reschedule_appointment`, `cancel_appointment`, and
`escalate_to_human`. Webhooks keep their configured HTTP tool names, URL, method,
parameters and encrypted headers. No generic arbitrary-URL tool is offered.

Knowledge search reuses retrieval over the current agent's documents and Q&A.
Appointments use real business hours, service duration/buffers, existing bookings,
blocks and timezone. Connected Google availability fails closed. Mutations commit
before confirmation and enqueue the existing durable calendar sync. Google events
can remain pending: the agent must not claim external sync before it is synced.
Bookings created by a native tool have source `agent` and retain conversation and
agent ownership. Reschedule/cancel can access only the customer's authorized
appointments. Playground cannot create appointments or mutate human routing.
Use synthetic customer/widget conversations outside Playground for action tests.

Every call rechecks active state, tenant ownership, current permissions and tool
configuration, and validates JSON Schema with formats. External schema references
are not fetched. Five calls total per turn are allowed, including denied attempts.
Tool failures are returned to the model without exception details; completed
side effects are never automatically rolled back or replayed when inference fails.
Handoff uses existing routing, notifications, activity and human mode. A business
without a team can receive an unassigned conversation awaiting human attention.
Social handoff retains the existing delivery/uncertain-send behavior.

Migration `0046_tool_executions` creates a scoped audit before any side effect.
Audit contains provider/model/channel, redacted inputs, status, safe summary and
latency; arbitrary external response bodies and credential values are not stored.
`started` without a completion means uncertain execution. Check domain records
before retrying. `Message.tool_calls` links completed turn metadata to execution
IDs. Audit survives a provider error. It can be read by authenticated agency users
at `GET /api/conversations/{id}/tool-executions`, with conversation ownership checks.
Enable View agent activity in Playground to inspect it; polling shows durable
records and does not introduce streaming infrastructure.

Groq/Ollama models with unconfirmed tool support continue as chat without tools,
with UI and prompt warnings. Their permissions remain configured for a compatible
model. OpenAI and Anthropic retain their existing transport compatibility.
Runtime HTTP/MCP destinations use the strict private-address guard and no
redirects; the legacy HTTP development bypass is not used for runtime calls.
DNS rebinding remains a documented limitation of the shared URL guard.

Automated tests mock model transports while executing real domain services in the
disposable database. They do not establish live Groq acceptance or Google delivery.
Live acceptance requires a configured key or installed tool-capable Ollama model,
and synthetic accounts/calendars explicitly authorized for testing.

Schema validation uses the [jsonschema validator API](https://python-jsonschema.readthedocs.io/en/stable/validate/).
