# Native appointments

The `/appointments` route uses the existing authenticated API and agency ownership
checks. Migration `0040_native_appointments` follows `0039_native_automations`.
It adds appointments, service definitions, weekly availability and blocked periods,
plus business timezone/slot spacing and the agent booking capability.

Configure a business timezone explicitly in appointment settings (existing
businesses default to UTC), create active services and add weekly intervals.
Weekdays use Monday=0 through Sunday=6. UTC instants are persisted; business-local
wall times are used to generate slots. Durations and both buffers must fit within
one working interval. Each business has one shared capacity across its services.
All booking/configuration mutations serialize on the owned Client row, then
recheck availability. Terminal appointments cannot be reopened. DELETE cancels
rather than erasing the audit trail. Google Calendar integration extends the existing external identifiers; see below.

The API exposes `/appointments` CRUD and availability, cancel, complete, no-show
and reschedule operations; `/appointment-services`; `/availability` GET/PUT;
and `/appointment-blocks` GET/POST/DELETE. Lists use business-local date ranges
(maximum 93 days) and support service, status and customer search filters.

Enable `appointments_enabled` per agent to add four native tools: availability,
create, reschedule and cancel. Availability also discovers active services and
business-local current time. Tools run directly in Python, use separate database
transactions, and confirm success only after commit. They are not exposed in
playground. Customer booking access is restricted to the current conversation or
its verified contact within the same business. Phone/email values supplied by
the model are not authorization credentials. WhatsApp and widget completion
paths supply the conversation context.

Appointment events extend the existing automation queue: created, rescheduled,
cancelled, completed and upcoming. Upcoming checkpoints use 15/30/60/120/720/1440/
2880 minutes of lead time. Revisions invalidate pending reminders after changes;
each queued action rechecks the revision and status. There is no second scheduler.
Message reminders need an existing linked conversation and remain subject to
channel reply-window and delivery protections. Manual appointments without a
conversation cannot send a message solely from a telephone number. External
requests already in flight cannot be recalled by cancelling an appointment.

Message variables are an explicit whitelist including appointment times/status,
customer name/phone/email, service name/duration and client name. The 24-hour and
2-hour templates populate normal automation definitions. No live WhatsApp or AI
provider acceptance is implied by mocked tests.

## Google Calendar (0041)

The existing routes and shared booking engine now support one Google calendar per
client. The Google transport is server-only. Configure `GOOGLE_CALENDAR_CLIENT_ID`,
`GOOGLE_CALENDAR_CLIENT_SECRET`, and `GOOGLE_CALENDAR_REDIRECT_URI`; enable the
Google Calendar API in the Google Cloud project and configure a Web application
OAuth client and its consent screen/test users. Keep the existing `ENCRYPTION_KEY`
stable. `CALENDAR_WORKER_ENABLED` defaults to true; disable it for isolated tests.

The exact default local redirect URI is:
`http://localhost:8000/api/appointment-calendars/google/callback`.
For a deployed gateway, set the redirect URI to the actual HTTPS origin followed
by `/api/appointment-calendars/google/callback` and register that identical URI
in Google Cloud. `FRONTEND_URL` determines the return to `/appointments`.
No production domain is assumed. The preview API's internal network deliberately
cannot contact Google; live OAuth needs an explicitly configured development host.

OAuth uses a ten-minute hashed, one-use state bound to the signed-in user,
agency and client, plus PKCE. Tokens are encrypted with the existing secret helper;
responses use explicit safe fields. Offline consent requests Calendar events,
calendar-list read, free/busy and account-email scopes. Declined/partial consent
is rejected. See Google's [web server OAuth guide](https://developers.google.com/identity/protocols/oauth2/web-server)
and [Calendar API reference](https://developers.google.com/workspace/calendar/api/v3/reference).

New endpoints, relative to `/api/appointment-calendars`:

- `GET /{client_id}/google`: safe connection and synchronization status.
- `POST /{client_id}/google/connect`: start backend OAuth.
- `GET /google/callback`: authenticated, user-bound OAuth callback.
- `GET /{client_id}/google/calendars`: writable calendars (paginated internally).
- `PUT /{client_id}/google/calendar`: select a verified writable calendar.
- `DELETE /{client_id}/google`: erase stored tokens and disconnect locally.
- `POST /{client_id}/google/retry`: retry failed synchronization.

Disconnect retains external events and their mappings. It does not revoke the
Google account's grant globally (that could affect another client). A user may
revoke the app separately in Google account settings. Reconnect the same account
and calendar to resume mapped work. A selected calendar cannot be changed after
appointments have been linked; mappings are never silently retargeted.

Availability checks fail closed when a connected calendar cannot be read. Normal
queries use FreeBusy. Rescheduling a linked appointment enumerates expanded events
to exclude only its own verified event while retaining overlapping external events,
including all-day events. Local working hours, blocks, service duration/buffers,
minimum notice and booking horizon still apply in the client's IANA timezone.
Google does not provide atomic free/busy-and-book transactions: an independent
Google writer can create a conflicting event after the check.

Booking transactions persist deterministic event IDs, calendar IDs and pending
synchronization on the appointment row. A background worker locks the same client
row as booking mutations, sends the latest appointment state and records success
or a sanitized error. Retries survive restarts, use bounded backoff and stop after
five failures until explicitly retried. An uncertain insert uses the same event ID;
updates/deletes verify private appointment/client markers. Tokens, raw provider
errors and Google event content are not logged. A Google outage does not erase a
saved appointment or falsely mark it synced. Manual and AI responses include sync
status, separate from the appointment's saved status.

Synchronization is outbound for linked bookings; external busy events are read
on demand. There is no webhook import of edits made directly in Google into Tkila
appointments. Existing bookings are not bulk imported; a later booking mutation
can link them. Calendar selection does not automatically move historical events.

Settings add optional service price (no invented price or currency) and color,
minimum notice in minutes, booking horizon in days, and reminder timing preferences
(120/1440 minutes). Preferences alone do not dispatch messages or create automation
rules. Existing explicit reminder automations remain authoritative; email delivery
is not implemented. Apple/iCloud is a labeled future CalDAV integration only.

Verification for this extension: 17 isolated PostgreSQL tests cover native booking
regressions, OAuth state/replay and encrypted storage, tenant route isolation,
free/busy failure handling, all-day/paginated events, event ownership, uncertain
insert recovery, settings limits and native-agent synchronization. These use
mocked Google transport; they do not establish a live Google consent grant or
external-account delivery. The full migration chain was also applied to the
disposable preview database through `0041_appointment_calendars`.
