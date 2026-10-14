# Functional agent objectives

The existing agent catalog owns typed defaults and configuration schemas in
`services/agent_catalog/objective_config.py`. Agent create/update validates those
settings in `services/objectives.py`, derives native tool grants and synchronizes
rules in the same transaction. There is no separate runtime or scheduling engine.
`POST /api/catalog/objective-configuration/{client_id}` previews effective grants
without saving. Tenant ownership is checked before reading business readiness.

Migration 0048 adds objective settings, a managed-mode flag, nullable automation
ownership metadata and deterministic lead-profile fields. Legacy agents remain
unmanaged until their objectives are explicitly edited. Old rules remain custom.
Normal name/model edits do not adopt old agents or restore revoked permissions.

## Managed rules

A unique agent/objective/rule key preserves each rule's identity across edits.
Follow-up creates one conversation-inactivity rule: after an ordinary assistant
reply, send the first message, wait the configured second delay, then optionally
send one more. Attempts are limited to two. New conversation activity, human mode,
agent deactivation and objective removal prevent subsequent sends. Playground,
historical and automation-generated messages do not initiate this behavior.
Changing a setting cancels pending old-revision jobs; follow-up changes apply to
subsequent assistant replies. It does not retroactively contact dormant leads.

Appointment reminders manage separate confirmation, first-reminder and second-
reminder rules. The existing appointment queue reschedules upcoming reminders on
configuration changes and appointment revisions. Post-service follow-up uses the
real appointment-completed event. Messages require a linked customer conversation
and use its original channel, including existing delivery windows and policies.
Appointment message variables are validated against the existing engine. Generic
follow-up messages currently support plain text, not personalization variables.

Disabling an objective pauses only its own rules and retains its configuration.
Advanced automation endpoints preserve custom flows and reject direct edits to
managed rules. Rule revisions and queued work remain inside the existing engine.

## Runtime and integrations

Knowledge objectives control retrieval sources and the existing knowledge tool.
Calendar permissions and service selections are validated again when executing
availability, booking, rescheduling and cancellation. Internal calendars require
services and working hours; choosing Google additionally requires its connection.
Handoff keywords invoke the existing executor and human Inbox state. Unresolved
requests use the same model tool; failed-attempt counting is not implemented.
Lead qualification stores explicitly selected customer fields and deterministically
classifies cold, warm (need collected), or hot (need, budget and date collected).
Sales uses documented knowledge/context and model instructions. Native order and
inventory objectives remain disabled because no semantic connector exists.

The sidebar and normal builder focus on objectives. Technical custom flows are
available under Agent > Advanced; `/automations` and its endpoints remain intact.
External AI and delivery acceptance requires configured providers/channels; mocked
provider tests are not proof of external delivery.
