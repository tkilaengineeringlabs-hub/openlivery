export type Trigger = "message_received" | "client_created" | "conversation_inactive" | "appointment_created" | "appointment_rescheduled" | "appointment_cancelled" | "appointment_completed" | "appointment_upcoming";
export type ActionType = "send_message" | "delay" | "handoff_to_human" | "http_request";
export type ConditionField = "message.text" | "channel" | "client.name" | "client.industry" | "conversation.mode";
export type Operator = "equals" | "not_equals" | "contains" | "not_contains" | "exists" | "not_exists";
export type Condition = { field: ConditionField; operator: Operator; value: string };
export type Action = { id: string } & (
  { type: "send_message"; text: string } |
  { type: "delay"; amount: number; unit: "minutes" | "hours" | "days" } |
  { type: "handoff_to_human" } |
  { type: "http_request"; method: "GET" | "POST" | "PUT" | "PATCH"; url: string; headers: Record<string, string>; query: Record<string, string>; body: Record<string, unknown> }
);
export type Draft = { template_id?: string | null; name: string; client_id: string | null; enabled: boolean; trigger_type: Trigger; trigger_config: { minutes?: number }; conditions: Condition[]; actions: Action[] };
export type Automation = Draft & { id: string; last_run_at: string | null; last_run_status: RunStatus | null };
export type RunStatus = "success" | "failed" | "running" | "skipped";
export type Run = { id: string; event_type: Trigger; status: RunStatus; started_at: string; completed_at: string | null; actions_executed: number; action_count: number; error: string | null; duration_seconds: number | null };
export const triggers: Trigger[] = ["message_received", "client_created", "conversation_inactive", "appointment_created", "appointment_rescheduled", "appointment_cancelled", "appointment_completed", "appointment_upcoming"];
export const actionTypes: ActionType[] = ["send_message", "delay", "handoff_to_human", "http_request"];
export const conditionFields: ConditionField[] = ["message.text", "channel", "client.name", "client.industry", "conversation.mode"];
export const operators: Operator[] = ["equals", "not_equals", "contains", "not_contains", "exists", "not_exists"];
export const inactivityMinutes = [5, 15, 30, 60, 120, 360, 720, 1440, 2880];
export function newAction(type: ActionType, id = crypto.randomUUID()): Action {
  switch (type) {
    case "send_message": return { id, type, text: "" };
    case "delay": return { id, type, amount: 30, unit: "minutes" };
    case "handoff_to_human": return { id, type };
    case "http_request": return { id, type, method: "POST", url: "", headers: {}, query: {}, body: {} };
  }
}

export const upcomingMinutes = [15, 30, 60, 120, 720, 1440, 2880];
