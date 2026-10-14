import { strict as assert } from "node:assert";
import { test } from "node:test";
import { catalogTemplates, createBlocks, prepareBlocks, selectedTemplates, toggleSelection } from "./selection";
import { simpleTemplate } from "./templates";

test("cross-category selection retains five independent editable blocks", () => {
  let ids: string[] = [];
  for (const id of ["confirmation", "reminder24", "reminder2", "followUp", "handoff"]) ids = toggleSelection(ids, id);
  assert.equal(ids.length, 5);
  assert.equal(toggleSelection(ids, "newLead"), ids);
  assert.equal(toggleSelection(ids, "outOfHours"), ids);
  assert.equal(toggleSelection(ids, "missing"), ids);
  assert.equal(toggleSelection(ids, "reminder24").length, 4);
  const blocks = createBlocks(ids, "business-a", t => t.id, () => "Hello", "human");
  assert.equal(new Set(blocks.map(b => b.id)).size, 5);
  blocks[1].draft.enabled = false;
  const batch = prepareBlocks(blocks);
  assert.equal(batch.length, 5);
  assert.equal(batch[1].configuration.enabled, false);
  assert.ok(batch.every(b => b.configuration.client_id === "business-a"));
  assert.deepEqual(prepareBlocks(blocks), batch); // Retry IDs/configurations remain stable.
  for (const block of blocks) assert.ok(simpleTemplate(block.draft));
  assert.equal(selectedTemplates(["newLead", "handoff"]).length, 1);
});

test("recommended catalog filters use backend IDs and keep selections across categories", () => {
  assert.deepEqual(catalogTemplates(true, ["confirmation", "handoff"], "all").map(t => t.id), ["confirmation", "handoff"]);
  assert.deepEqual(catalogTemplates(true, ["confirmation", "handoff"], "care").map(t => t.id), ["handoff"]);
  assert.ok(catalogTemplates(false, [], "all").some(t => t.unavailable));
});

test("batch HTTP input is parsed safely and mixed business configuration is rejected", () => {
  const blocks = createBlocks(["webhook", "confirmation"], "a", t => t.id, () => "Hello", "human");
  const http = blocks.find(b => b.template.id === "webhook")!;
  http.body = '{"event":"fixture"}';
  const action = prepareBlocks(blocks).find(b => b.configuration.template_id === "webhook")!.configuration.actions[0];
  assert.equal(action.type, "http_request");
  if (action.type === "http_request") assert.deepEqual(action.body, { event: "fixture" });
  http.body = "[]";
  assert.throws(() => prepareBlocks(blocks));
  http.body = "{}";
  blocks[0].draft.client_id = "b";
  assert.throws(() => prepareBlocks(blocks));
});
