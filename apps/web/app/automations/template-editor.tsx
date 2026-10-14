"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { useToast } from "@/components/toast";
import { PageHead } from "@/components/ui";
import type { Client } from "@/types";
import { TemplateFields } from "./template-fields";
import { AutomationHistory } from "./history";
import { templateDraft, type Template } from "./templates";
import { type Automation, type Draft } from "./types";

export function TemplateEditor({ template, initial, onClose, onSaved, onAdvanced }: {
  template: Template; initial: Automation | null; onClose: () => void; onSaved: () => void;
  onAdvanced: (draft: Draft, id?: string) => void;
}) {
  const { t } = useLanguage();
  const toast = useToast();
  const [draft, setDraft] = useState<Draft>(() => initial ? {
    template_id: initial.template_id, name: initial.name, client_id: initial.client_id, enabled: initial.enabled,
    trigger_type: initial.trigger_type, trigger_config: initial.trigger_config, conditions: initial.conditions, actions: initial.actions,
  } : templateDraft(template, t(`automations.catalog.${template.id}.name`), t(template.category === "appointments" ? template.id === "afterAppointment" ? "automations.completedMessage" : "automations.defaultMessage" : "automations.followUpMessage"), t("automations.keyword")));
  const [clients, setClients] = useState<Client[]>([]);
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [body, setBody] = useState(() => JSON.stringify(draft.actions[0].type === "http_request" ? draft.actions[0].body : {}, null, 2));
  useEffect(() => { api<Client[]>("/clients").then(setClients).catch(() => setFailed(true)).finally(() => setLoaded(true)); }, []);
  const action = draft.actions[0];
  function patch(values: Partial<Draft>) { setDirty(true); setDraft(current => ({ ...current, ...values })); }
  function prepared(): Draft | null {
    if (action.type !== "http_request") return draft;
    try {
      const parsed: unknown = JSON.parse(body);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
      return { ...draft, actions: [{ ...action, body: parsed as Record<string, unknown> }] };
    } catch { toast.error(t("automations.invalidJson")); return null; }
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    const values = prepared();
    if (!values) return;
    setBusy(true);
    try {
      await api(initial ? `/automations/${initial.id}` : "/automations", { method: initial ? "PATCH" : "POST", body: JSON.stringify(values) });
      toast.success(t(initial ? "automations.saved" : "automations.created")); onSaved();
    } catch { toast.error(t("automations.error")); }
    finally { setBusy(false); }
  }
  function close() { if (!dirty || window.confirm(t("automations.discard"))) onClose(); }
  return <div className="page automations-page">
    <button className="button ghost" disabled={busy} onClick={close}><ArrowLeft size={18} />{t("automations.back")}</button>
    <PageHead title={t(`automations.catalog.${template.id}.name`)} description={t(`automations.catalog.${template.id}.description`)} />
    {initial && <p className="field-help">{t("automations.editHelp")}</p>}
    <form className="automation-form template-form" onSubmit={save}><fieldset className="automation-fieldset" disabled={busy}>
      <TemplateFields template={template} draft={draft} clients={clients} loaded={loaded} failed={failed} patch={patch} body={body} setBody={value => { setDirty(true); setBody(value); }} />
      <div className="automation-controls"><button type="submit" className="button primary" disabled={busy || !loaded || failed || !clients.some(c => c.id === draft.client_id)}>{t(busy ? "automations.saving" : initial || !draft.enabled ? "automations.save" : "automations.activate")}</button><button type="button" className="button secondary" onClick={close}>{t("automations.cancel")}</button></div>
      <button type="button" className="button ghost" onClick={() => { const values = prepared(); if (values) onAdvanced(values, initial?.id); }}>{t("automations.advancedEdit")}</button>
    </fieldset></form>
    {initial && <details className="template-history"><summary>{t("automations.history")}</summary><AutomationHistory id={initial.id} /></details>}
  </div>;
}
