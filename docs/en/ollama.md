# Ollama with Tkila Box on macOS and Docker

Ollama runs through the existing agent runtime: prompts, history, retrieved
knowledge, tool permissions and conversation persistence are shared with OpenAI
and Anthropic. There is no separate runtime. Apply migration
`0044_ollama_provider` through the normal deployment migration process before
using the updated API; it only adds nullable provider-connection columns.

## Setup

1. Install and start [Ollama for macOS](https://ollama.com/download/mac).
2. Choose and download a model yourself, for example `ollama pull qwen3:latest`.
   This is an example, not an assumed installed model. Tkila never downloads models.
3. Confirm the host server with `curl --fail http://localhost:11434/api/tags`.
4. In Tkila Settings → AI providers → Ollama, enter a connection name and
   `http://host.docker.internal:11434` when the API runs in Docker Desktop on Mac.
   For an API running directly on the Mac, use `http://localhost:11434`.
   Container localhost refers to that container, not the Mac.
5. Click **Test connection**, select an optional default from the returned list,
   and **Save**. **Refresh models** queries the instance again without restarting.
6. Click **Test selected model**. This sends `Responde únicamente: OK` to the
   selected model without creating a customer conversation. Success requires the
   actual response to be exactly `OK`; a different response is reported honestly.
7. Create/edit an agent, select Ollama and an installed model, save, and try it in
   the existing playground. The agency's connection name and URL are displayed.

If Docker cannot reach the host listener, configure the macOS Ollama app to
listen beyond loopback, then restart that app:

```bash
launchctl setenv OLLAMA_HOST "0.0.0.0:11434"
```

This exposes the listener to reachable network interfaces; restrict access with
your host/network firewall. Do not expose unauthenticated Ollama publicly.
For a CLI-managed server, quit the app's existing server first, then run
`OLLAMA_HOST=0.0.0.0:11434 ollama serve` instead. See the
[official server configuration](https://docs.ollama.com/faq#setting-environment-variables-on-mac).
No browser CORS change is needed: requests originate in the backend.

With the normal API container already running, check Docker-to-Mac connectivity:

```bash
docker compose --env-file .env.docker exec api python -c 'import urllib.request; print(urllib.request.urlopen("http://host.docker.internal:11434/api/tags", timeout=5).status)'
```

Quick host inference (after downloading that example model):

```bash
curl --fail --max-time 180 http://localhost:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3:latest","messages":[{"role":"user","content":"Responde únicamente: OK"}],"stream":false}'
```

Use an installed model's exact name if different. These commands are manual live
checks; automated tests mock Ollama and cannot establish real host connectivity.

## Configuration and boundaries

- `OLLAMA_BASE_URL` is optional. Saved agency URL wins; otherwise the installation
  default is used. Without the variable, Docker uses `host.docker.internal:11434`
  and direct local execution uses `localhost:11434`, both over HTTP.
- `OLLAMA_TIMEOUT_SECONDS=180` bounds each generation request (5–600 seconds).
  Connection establishment has a 5-second limit; discovery/show have a 15-second
  total limit. Generation has an absolute deadline even for drip-fed responses.
- `OLLAMA_ALLOWED_PRIVATE_ORIGINS` is a JSON array controlled by the deployment
  administrator. Defaults allow HTTP port 11434 on localhost, 127.0.0.1, ::1 and
  host.docker.internal only. For another private host/port, explicitly add its
  exact origin. To disallow all private endpoints, set `[]`.
- Public HTTP(S) endpoints pass the shared strict SSRF guard. URL credentials,
  paths, queries and fragments are rejected; redirects and environment proxies
  are disabled. DNS rebinding remains the shared guard's known limitation.
  Allowlisted local origins are trusted installation services reachable by every
  agency that configures them, not independent tenant sandboxes. For hosted
  untrusted tenants remove those origins and enforce network egress controls.
- One connection per provider per agency, matching the original credential model.
  Agents store `provider="ollama"` and the exact `model` identifier. No redundant
  connection ID is needed. Default model only seeds selection; it does not update
  existing agents. Missing models fail explicitly when selected or used.
- No API key is required. An optional bearer token for a remote proxy is stored
  encrypted in the existing credential field. Blank input preserves it; the
  explicit clear checkbox removes it. Changing an authenticated endpoint requires
  a new token or explicit clearing, preventing forwarding the old token elsewhere.
- Tools are enabled only when `/api/show` explicitly includes `tools`. Missing
  metadata means unconfirmed and fails closed for agents with tools. Every call
  is checked against the runtime's authorized ToolRegistry and uses its existing
  executor. Five tool rounds, at most sixteen calls per round; unknown tools never
  execute. Model quality and argument correctness remain model-dependent.
- Vision metadata is displayed when reported by Ollama, but inbound image/audio
  preprocessing still uses the existing OpenAI credential path. This adapter
  accepts normalized text messages. It does not add vision upload, embeddings,
  streaming or structured output support.
- Failure responses use stable `ollama.*` codes translated by the web UI; upstream
  response bodies and secrets are never returned as error details.

## API and verification

Existing `/api/providers` GET, PUT/DELETE `/{provider}`, POST `/{provider}/test`
and `/{provider}/validate` now support Ollama. Added:

- `GET /api/providers/ollama/capabilities?model=...`: per-instance model capabilities.
- `POST /api/providers/ollama/probe` with `{"model":"installed-name"}`: real isolated inference.

The existing test endpoint returns freshly discovered models; refresh reuses it.
The validate endpoint accepts the draft connection without storing it. Probe and
model/capability reads use only the authenticated agency's saved connection.

```bash
bash scripts/verify-api.sh -q tests/test_ollama.py tests/test_agent_architecture.py tests/test_flows.py
PATH=/usr/local/bin:$PATH make verify-web WEB_BUNDLER_FLAGS=--webpack
```

The explicit Node path is specific to the inspected Mac; use your supported Node
runtime elsewhere. See [isolated verification](local-verification.md).
API shapes follow the [official Ollama chat API](https://docs.ollama.com/api/chat)
and [tool calling guide](https://docs.ollama.com/capabilities/tool-calling).
