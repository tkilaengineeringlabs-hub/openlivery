# Visual agent builder

`/agents/new` opens eight guided steps: business, objectives, channels, tools,
model, template, personalization and review. Advanced configuration switches to
the existing creation form. Existing agents retain their instructions and defaults;
missing objectives or a template display as Custom.

The wizard saves through the existing `/api/agents` POST/PATCH endpoints. Migration
`0045_agent_builder` adds channel preferences, explicit tool references, tone,
greeting guidance and the knowledge permission to the same Agent table. The
business-scoped `/api/catalog/agent-configuration/{client_id}` returns calendar
readiness and reusable configured tools, without credentials. No new runtime or
provider table is introduced.

Model lists come from configured provider connections. Ollama models must still
exist at save time. Tool-using Ollama agents require confirmed tool capability.
OpenAI and Anthropic use their existing adapters. Gemini is shown as unavailable
because there is no executable adapter yet. No models are downloaded automatically.

Tools are explicit permissions. Native appointment permissions remain a bundle
and require services and working hours. Google Calendar uses the existing native
appointment integration. Shared HTTP/MCP tools must belong to this business and
agency; disabling or deleting the source revokes runtime access. Knowledge can be
disabled independently. Objectives describe tasks and never grant tools by themselves.
Templates supply starter instructions; their tool, channel and automation previews
are suggestions, not automatic assignments.

Channel selections are a saved plan: connect and assign real channels from the
business page. Existing channel assignments are never moved by the wizard.
Automation recommendations require a separate confirmation with editable messages.
They apply to the business, not just the agent. Existing rules are preserved and
must be reviewed in Automations; they are not silently enabled or overwritten.

Test agent opens the existing playground with the saved model, prompt, business
context, history and allowed tools. Playground conversations stay outside customer
reports. Native appointment writes and human handoff remain disabled there; custom
HTTP/MCP tools can perform real actions. No AI response is simulated.

## Local acceptance

Use the isolated preview described in [local-verification.md](local-verification.md).
For an explicitly authorized local Ollama test:

```bash
make preview-api-ollama
make preview-web WEB_BUNDLER_FLAGS=--webpack
```

A previously built API image can be reused with `PREVIEW_BUILD_FLAGS=--no-build`.
Open `http://localhost:13000`. Configure the preview Ollama connection with
`http://ollama-preview:11434`: this internal gateway forwards only model discovery,
capability checks and chat to Ollama on the Mac. The normal Docker stack uses
`http://host.docker.internal:11434`; see [ollama.md](ollama.md).

The preview uses synthetic temporary data and disabled background workers.
Automation definitions can be saved, but scheduled actions are not processed in
this preview. Data survives browser refresh and API restart, but not destruction
or recreation of its tmpfs database container. Do not use it for customer data.
