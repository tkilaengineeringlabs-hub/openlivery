import { strict as assert } from "node:assert";
import { test } from "node:test";
import { automationTemplates, simpleTemplate, templateDraft } from "./templates";

test("supported templates round-trip through the same rule structure", () => {
  for (const template of automationTemplates.filter(item => !item.unavailable)) {
    const draft = templateDraft(template, "Test", "Hello", "human");
    draft.client_id = "business-a";
    assert.equal(simpleTemplate(JSON.parse(JSON.stringify(draft)))?.id, template.id);
    assert.equal(draft.actions[0].type, template.action);
    assert.equal(draft.trigger_type, template.trigger);
    assert.equal(draft.trigger_config.minutes, template.minutes);
    assert.notEqual(templateDraft(template, "Test", "Hello", "human").actions[0].id, draft.actions[0].id);
  }
});

test("legacy and advanced rules never silently lose options in the simple form", () => {
  const template = automationTemplates.find(item => item.id === "reminder24")!;
  const draft = { ...templateDraft(template, "Test", "Hello", "human"), client_id: "business-a" };
  assert.equal(simpleTemplate({ ...draft, template_id: null }), undefined);
  assert.equal(simpleTemplate({ ...draft, client_id: null }), undefined);
  assert.equal(simpleTemplate({ ...draft, actions: [...draft.actions, { id: "extra", type: "handoff_to_human" }] }), undefined);
  assert.equal(simpleTemplate({ ...draft, conditions: [{ field: "channel", operator: "equals", value: "widget" }] }), undefined);
  assert.equal(simpleTemplate({ ...draft, trigger_type: "appointment_cancelled" }), undefined);
  assert.equal(simpleTemplate({ ...draft, template_id: "unknown" }), undefined);
});


test("unavailable catalog entries cannot create misleading rules", () => {
  for (const template of automationTemplates.filter(item => item.unavailable)) {
    assert.throws(() => templateDraft(template, "Test", "Hello", "human"));
  }
});
