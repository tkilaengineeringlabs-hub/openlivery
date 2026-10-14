import type { automations } from "../../lib/i18n/dicts/automations";
import { newAction, type Draft, type Trigger } from "./types";

export const categories = ["appointments", "sales", "care", "integrations"] as const;
type Category = typeof categories[number];
type Field = "minutes" | "message" | "keyword" | "http";
export type Template = {
  id: keyof typeof automations.en.catalog; category: Category; trigger: Trigger; fields: readonly Field[];
  action: "send_message" | "handoff_to_human" | "http_request";
  minutes?: number; badge?: "recommended" | "popular"; unavailable?: boolean;
};
export const automationTemplates: Template[] = [
  { id: "confirmation", category: "appointments", trigger: "appointment_created", action: "send_message", fields: ["message"] },
  { id: "reminder24", category: "appointments", trigger: "appointment_upcoming", minutes: 1440, action: "send_message", fields: ["minutes", "message"], badge: "recommended" },
  { id: "reminder2", category: "appointments", trigger: "appointment_upcoming", minutes: 120, action: "send_message", fields: ["minutes", "message"] },
  { id: "afterAppointment", category: "appointments", trigger: "appointment_completed", action: "send_message", fields: ["message"] },
  { id: "followUp", category: "sales", trigger: "conversation_inactive", minutes: 30, action: "send_message", fields: ["minutes", "message"], badge: "popular" },
  { id: "recover", category: "sales", trigger: "conversation_inactive", minutes: 1440, action: "send_message", fields: ["minutes", "message"] },
  { id: "newLead", category: "sales", trigger: "message_received", action: "send_message", fields: [], unavailable: true },
  { id: "welcome", category: "care", trigger: "message_received", action: "send_message", fields: [], unavailable: true },
  { id: "handoff", category: "care", trigger: "message_received", action: "handoff_to_human", fields: ["keyword"] },
  { id: "outOfHours", category: "care", trigger: "message_received", action: "send_message", fields: [], unavailable: true },
  { id: "webhook", category: "integrations", trigger: "message_received", action: "http_request", fields: ["http"] },
  { id: "notify", category: "integrations", trigger: "appointment_created", action: "http_request", fields: ["http"] },
];

export function templateDraft(template: Template, name: string, message: string, keyword: string): Draft {
  if (template.unavailable) throw new Error("Template is not supported by the automation engine");
  const action = newAction(template.action);
  if (action.type === "send_message") action.text = message;
  return { template_id: template.id, name, client_id: null, enabled: true,
    trigger_type: template.trigger, trigger_config: template.minutes ? { minutes: template.minutes } : {},
    conditions: template.fields.includes("keyword") ? [{ field: "message.text", operator: "contains", value: keyword }] : [], actions: [action] };
}

// Only losslessly representable rules may reopen in the simplified editor.
// Origin alone never authorizes dropping fields added in advanced mode or by API.
export function simpleTemplate(draft: Draft): Template | undefined {
  const template = automationTemplates.find(item => item.id === draft.template_id && !item.unavailable);
  if (!template || !draft.client_id || draft.actions.length !== 1 || draft.actions[0].type !== template.action) return;
  if (draft.actions[0].type === "http_request" && Object.keys(draft.actions[0].query).length) return;
  if (!template.fields.includes("http") && draft.trigger_type !== template.trigger) return;
  if (Object.keys(draft.trigger_config).some(key => key !== "minutes")) return;
  const keyword = template.fields.includes("keyword");
  if (draft.conditions.length !== (keyword ? 1 : 0)) return;
  if (keyword && (draft.conditions[0].field !== "message.text" || draft.conditions[0].operator !== "contains")) return;
  return template;
}
