# Groq

Configure Groq under Settings, enter a connection name and API key, and test the
connection. Refresh fetches models from the official Groq models API. Save the
connection and optionally a default model. Test selected model sends a real
`Responde únicamente con: OK` request without creating a conversation.

The key is encrypted using the existing provider credential mechanism and never
returned to the browser. The optional backend-only `GROQ_API_KEY` is a shared
installation fallback; each agency's saved connection overrides it. Do not set a
global fallback if agencies must each provide their own credential.

Create or edit an agent, select Groq and a discovered model, then open its existing
playground. The same runtime supplies instructions, context, knowledge, history
and permissions. Agents retain the existing provider/model fields and resolve the
unique provider connection within their agency. No additional connection table or
schema migration is introduced.

Groq models include products that may not accept chat completions. Discovery does
not guarantee chat compatibility: use the selected-model probe. Groq's models API does not advertise tool capabilities. A small forced-function
inference request confirms support without executing a tool; the result is cached
for five minutes per credential and model. This check consumes provider usage.
Unknown tool capabilities fail closed. Confirmed models use the existing tool
allowlist and executor. Vision preprocessing still uses the
existing OpenAI path. Streaming and structured output are unavailable in this
adapter. Requests have bounded deadlines, no automatic generation retries and
safe errors for authorization, rate limits, timeout and malformed responses.

Endpoints reuse `/api/providers/groq` (PUT/DELETE), `/test` and `/validate` (POST),
and add `/models` (GET), `/capabilities?model=...` (GET), `/probe` (POST).
All require agency authentication. Real cloud validation requires a user-supplied
key and may incur provider usage; automated tests use HTTP mocks.

API behavior is based on the [official Groq API reference](https://console.groq.com/docs/api-reference).
