import { automationTemplates, templateDraft, type Template } from "./templates";
import type { Draft } from "./types";

export function toggleSelection(ids: string[], id: string): string[] {
  if (!automationTemplates.some(t => t.id === id && !t.unavailable)) return ids;
  return ids.includes(id) ? ids.filter(value => value !== id) : [...ids, id];
}
export function selectedTemplates(ids: string[]): Template[] {
  return automationTemplates.filter(t => !t.unavailable && ids.includes(t.id));
}
export function catalogTemplates(recommended: boolean, ids: string[], category: string) {
  return automationTemplates.filter(t => (!recommended || ids.includes(t.id)) && (category === "all" || t.category === category));
}
export type Block = { id: string; template: Template; draft: Draft; body: string };
export function createBlocks(ids: string[], clientId: string, name: (t: Template) => string, message: (t: Template) => string, keyword: string): Block[] {
  return selectedTemplates(ids).map(template => ({ id: crypto.randomUUID(), template, draft: { ...templateDraft(template, name(template), message(template), keyword), client_id: clientId }, body: "{}" }));
}
export function prepareBlocks(blocks: Block[]) {
  if (!blocks.length || blocks.some(b => !b.draft.client_id) || new Set(blocks.map(b => b.draft.client_id)).size !== 1) throw new Error("Business is required");
  return blocks.map(block => {
    const action = block.draft.actions[0];
    let draft = block.draft;
    if (action.type === "http_request") {
      const body: unknown = JSON.parse(block.body);
      if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("Invalid JSON body");
      draft = { ...draft, actions: [{ ...action, body: body as Record<string, unknown> }] };
    }
    return { id: block.id, configuration: draft };
  });
}
