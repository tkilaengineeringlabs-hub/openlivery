import type { IndustryLabel } from "@/types";
export type ObjectiveDefinition = { id: string; label: IndustryLabel; recommended_tools: string[]; suggested_automations: string[]; requires_configuration: boolean; category: string; available: boolean; default_config: Record<string, unknown>; configuration_schema: { properties: Record<string, { type?: string; enum?: string[]; items?: { enum?: string[] }; minimum?: number; maximum?: number; title?: string }> } };
export type AgentTemplate = { id: string; name: IndustryLabel; industry: string; business_type: string; objectives: string[]; recommended_channels: string[]; recommended_tools: string[]; suggested_automations: string[]; description: IndustryLabel; default_tone: Tone; required_business_fields: string[]; optional_business_fields: string[]; handoff_rules: string[]; tags: string[]; version: number; active: boolean };
export type AgentCatalog = { objectives: ObjectiveDefinition[]; templates: AgentTemplate[]; tools: { id: string; label: IndustryLabel }[]; providers: string[]; channels: string[] };
export type BuilderContext = { services?: { id: string; name: string }[]; appointments_ready: boolean; google_connected: boolean; tools: { id: string; name: string; description: string; type: string; agent_id: string }[] };
export const appointmentTools = ["check_appointment_availability", "create_appointment", "reschedule_appointment", "cancel_appointment"];
export const channels = ["whatsapp", "instagram", "messenger", "widget", "telegram", "mercado_libre", "amazon"] as const;
export type Channel = typeof channels[number];
export const tones = ["professional", "friendly", "warm", "direct", "formal"] as const;
export type Tone = typeof tones[number];
export const toggle = (items: string[], id: string) => items.includes(id) ? items.filter(item => item !== id) : [...items, id];
export function suggestedAutomationIds(catalog: AgentCatalog | null, objectives: string[], template?: AgentTemplate) {
  return [...new Set([...(catalog?.objectives.filter(o => objectives.includes(o.id)).flatMap(o => o.suggested_automations) || []), ...(template?.suggested_automations || [])])];
}
export type TemplateMatch = { template: AgentTemplate; score: number; reasons: Record<string, number>; exact_match: boolean; recommended: boolean; warnings: string[] };
export type TemplatePreview = { template: AgentTemplate; defaults: { objective_config?: Record<string, Record<string, unknown>>; template_id: string; name: string; objectives: string[]; selected_tools: string[]; selected_channels: string[]; tone: Tone; instructions: string }; warnings: string[]; unavailable_tools: string[]; missing_business_fields: string[]; google_connected: boolean; template_version: number; template_snapshot: AgentTemplate };
