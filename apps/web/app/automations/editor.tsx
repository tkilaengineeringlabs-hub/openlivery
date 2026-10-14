"use client";

import { FormEvent, useEffect, useState } from "react";
import { ArrowDown, ArrowLeft, ArrowUp, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { Alert, PageHead } from "@/components/ui";
import { useToast } from "@/components/toast";
import type { Client } from "@/types";
import { simpleTemplate } from "./templates";
import { AutomationHistory } from "./history";
import { actionTypes, conditionFields, inactivityMinutes, newAction, operators, triggers, upcomingMinutes } from "./types";
import type { Action, ActionType, Automation, Condition, Draft, Trigger } from "./types";

export function Pairs({ value, onChange, secret = false }: { value: Record<string, string>; onChange: (value: Record<string, string>) => void; secret?: boolean }) {
  const { t } = useLanguage();
  const entries = Object.entries(value);
  function change(index: number, key: string, val: string) { onChange(Object.fromEntries(entries.map((pair, i) => i === index ? [key, val] : pair))); }
  return <div className="automation-pairs">{entries.map(([key, val], index) => <div className="automation-pair" key={index}>
    <input aria-label={t("automations.key")} value={key} onChange={e => change(index, e.target.value, val)} maxLength={100} required />
    <input aria-label={t("automations.value")} type={secret ? "password" : "text"} autoComplete="off" value={val} onChange={e => change(index, key, e.target.value)} maxLength={4000} />
    <button type="button" className="icon-button" aria-label={t("automations.remove")} onClick={() => onChange(Object.fromEntries(entries.filter((_, i) => i !== index)))}><Trash2 size={16} /></button>
  </div>)}<button type="button" className="button secondary" disabled={entries.length >= 30 || "" in value} onClick={() => onChange({ ...value, "": "" })}><Plus size={16} />{t("automations.addPair")}</button></div>;
}

export function AutomationEditor({ initial, preset, onClose, onSaved }: { initial: Automation | null; preset?: Draft; onClose: () => void; onSaved: () => void }) {
  const { t } = useLanguage();
  const toast = useToast();
  const [draft, setDraft] = useState<Draft>(() => preset ?? (initial ? { template_id: initial.template_id, name: initial.name, client_id: initial.client_id, enabled: initial.enabled, trigger_type: initial.trigger_type, trigger_config: initial.trigger_config, conditions: initial.conditions, actions: initial.actions } : { name: "", client_id: null, enabled: true, trigger_type: "message_received", trigger_config: {}, conditions: [], actions: [] }));
  const [bodies, setBodies] = useState<Record<string, string>>(() => Object.fromEntries((preset?.actions || initial?.actions || []).filter(a => a.type === "http_request").map(a => [a.id, JSON.stringify(a.body, null, 2)])));
  const [clients, setClients] = useState<Client[]>([]);
  const [clientsFailed, setClientsFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"edit" | "history">("edit");
  useEffect(() => { api<Client[]>("/clients").then(setClients).catch(() => setClientsFailed(true)); }, []);
  function patch(values: Partial<Draft>) { setDraft(current => ({ ...current, ...values })); }
  function updateAction(index: number, action: Action) { patch({ actions: draft.actions.map((item, i) => i === index ? action : item) }); }
  function move(index: number, direction: number) {
    const actions = [...draft.actions];
    [actions[index], actions[index + direction]] = [actions[index + direction], actions[index]];
    patch({ actions });
  }
  function setTrigger(trigger_type: Trigger) {
    patch({ trigger_type, trigger_config: ["conversation_inactive", "appointment_upcoming"].includes(trigger_type) ? { minutes: 30 } : {},
      conditions: draft.conditions.filter(c => trigger_type !== "client_created" || c.field.startsWith("client.")),
      actions: draft.actions.filter(a => trigger_type !== "client_created" || a.type === "delay" || a.type === "http_request") });
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    let actions: Action[];
    try {
      actions = draft.actions.map(action => {
        if (action.type !== "http_request") return action;
        const body: unknown = JSON.parse(bodies[action.id] ?? JSON.stringify(action.body));
        if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error();
        return { ...action, body: body as Record<string, unknown> };
      });
    } catch { toast.error(t("automations.invalidJson")); return; }
    setBusy(true);
    try {
      await api(initial ? `/automations/${initial.id}` : "/automations", { method: initial ? "PATCH" : "POST", body: JSON.stringify({ ...draft, actions }) });
      toast.success(t(initial ? "automations.saved" : "automations.created")); onSaved();
    } catch { toast.error(t("automations.error")); }
    finally { setBusy(false); }
  }
  const availableActions = actionTypes.filter(type => draft.trigger_type !== "client_created" || type === "delay" || type === "http_request");
  return <div className="page automations-page">
    <button type="button" className="button ghost" onClick={onClose} disabled={busy}><ArrowLeft size={18} />{t("automations.back")}</button>
    <PageHead title={t(initial ? "automations.edit" : "automations.new")} description={t(initial ? "automations.editHelp" : "automations.description")} />
    {draft.template_id && !simpleTemplate(draft) && <p className="field-help">{t("automations.advancedWarning")}</p>}
    {initial && <div className="tabs"><button className={tab === "edit" ? "active" : ""} onClick={() => setTab("edit")}>{t("automations.editButton")}</button><button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>{t("automations.history")}</button></div>}
    {initial && tab === "history" ? <AutomationHistory id={initial.id} /> : <form onSubmit={save} className="automation-form">
      <fieldset disabled={busy} className="automation-fieldset">

      <section className="form-section"><div><h2>{t("automations.name")}</h2></div><div className="form-fields">
        <label>{t("automations.name")}<input required maxLength={180} value={draft.name} onChange={e => patch({ name: e.target.value })} /></label>
        <label>{t("automations.client")}<select value={draft.client_id || ""} onChange={e => patch({ client_id: e.target.value || null })}><option value="">{t("automations.allClients")}</option>{clients.map(client => <option key={client.id} value={client.id}>{client.name}</option>)}</select></label>
        {clientsFailed && <Alert>{t("automations.loadError")}</Alert>}
        <label className="automation-check"><input type="checkbox" checked={draft.enabled} onChange={e => patch({ enabled: e.target.checked })} />{t("automations.active")}</label>
      </div></section>
      <section className="form-section"><div><h2>{t("automations.when")}</h2><p>{t("automations.whenHelp")}</p></div><div className="form-fields">
        <label>{t("automations.event")}<select value={draft.trigger_type} onChange={e => setTrigger(e.target.value as Trigger)}>{triggers.map(trigger => <option key={trigger} value={trigger}>{t(`automations.trigger.${trigger}`)}</option>)}</select></label>
        {draft.trigger_type === "conversation_inactive" && <><label>{t("automations.duration")}<select value={draft.trigger_config.minutes} onChange={e => patch({ trigger_config: { minutes: Number(e.target.value) } })}>{inactivityMinutes.map(minutes => <option key={minutes} value={minutes}>{minutes < 60 ? minutes : minutes / 60} {t(minutes < 60 ? "automations.minutes" : "automations.hours")}</option>)}</select></label><p className="field-help">{t("automations.inactivityHelp")}</p></>}
        {draft.trigger_type === "appointment_upcoming" && <label>{t("automations.beforeAppointment")}<select value={draft.trigger_config.minutes} onChange={e => patch({ trigger_config: { minutes: Number(e.target.value) } })}>{upcomingMinutes.map(minutes => <option key={minutes} value={minutes}>{minutes < 60 ? minutes : minutes / 60} {t(minutes < 60 ? "automations.minutes" : "automations.hours")}</option>)}</select></label>}
        {draft.trigger_type === "client_created" && <p className="field-help">{t("automations.clientHelp")}</p>}
      </div></section>
      <section className="form-section"><div><h2>{t("automations.if")}</h2><p>{t("automations.ifHelp")}</p></div><div className="form-fields">
        {draft.conditions.map((condition, index) => <div className="automation-condition" key={index}>
          <label>{t("automations.field")}<select value={condition.field} onChange={e => patch({ conditions: draft.conditions.map((c, i) => i === index ? { ...c, field: e.target.value as Condition["field"] } : c) })}>{conditionFields.filter(field => draft.trigger_type !== "client_created" || field.startsWith("client.")).map(field => <option key={field} value={field}>{t(`automations.fields.${field}`)}</option>)}</select></label>
          <label>{t("automations.operator")}<select value={condition.operator} onChange={e => patch({ conditions: draft.conditions.map((c, i) => i === index ? { ...c, operator: e.target.value as Condition["operator"] } : c) })}>{operators.map(operator => <option key={operator} value={operator}>{t(`automations.operators.${operator}`)}</option>)}</select></label>
          {!(["exists", "not_exists"].includes(condition.operator)) && <label>{t("automations.value")}<input maxLength={2000} value={condition.value} onChange={e => patch({ conditions: draft.conditions.map((c, i) => i === index ? { ...c, value: e.target.value } : c) })} /></label>}
          <button className="icon-button" type="button" aria-label={t("automations.remove")} onClick={() => patch({ conditions: draft.conditions.filter((_, i) => i !== index) })}><Trash2 size={16} /></button>
        </div>)}
        {draft.conditions.some(c => c.field === "channel" || c.field === "conversation.mode") && <p className="field-help">{t("automations.channelValues")}</p>}
        <button className="button secondary" type="button" disabled={draft.conditions.length >= 20} onClick={() => patch({ conditions: [...draft.conditions, { field: draft.trigger_type === "client_created" ? "client.name" : "message.text", operator: "contains", value: "" }] })}><Plus size={16} />{t("automations.addCondition")}</button>
      </div></section>
      <section className="form-section"><div><h2>{t("automations.do")}</h2><p>{t("automations.doHelp")}</p></div><div className="form-fields">
        {draft.actions.map((action, index) => <article className="automation-action" key={action.id}>
          <div className="automation-action-head"><strong>{index + 1}. {t(`automations.action.${action.type}`)}</strong><div className="automation-controls">
            <button type="button" className="icon-button" aria-label={t("automations.up")} disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp size={16} /></button>
            <button type="button" className="icon-button" aria-label={t("automations.down")} disabled={index === draft.actions.length - 1} onClick={() => move(index, 1)}><ArrowDown size={16} /></button>
            <button type="button" className="icon-button" aria-label={t("automations.remove")} onClick={() => patch({ actions: draft.actions.filter((_, i) => i !== index) })}><Trash2 size={16} /></button>
          </div></div>
          <label>{t("automations.do")}<select value={action.type} onChange={e => updateAction(index, newAction(e.target.value as ActionType, action.id))}>{availableActions.map(type => <option key={type} value={type}>{t(`automations.action.${type}`)}</option>)}</select></label>
          {action.type === "send_message" && <><label>{t("automations.message")}<textarea required maxLength={8000} value={action.text} onChange={e => updateAction(index, { ...action, text: e.target.value })} /></label><p className="field-help">{t("automations.sendHelp")}</p>{draft.trigger_type.startsWith("appointment_") && <p className="field-help">{t("automations.variablesHelp")}</p>}</>}
          {action.type === "delay" && <div className="form-grid"><label>{t("automations.amount")}<input required type="number" min={1} max={{ minutes: 43200, hours: 720, days: 30 }[action.unit]} value={action.amount} onChange={e => updateAction(index, { ...action, amount: Number(e.target.value) })} /></label><label>{t("automations.unit")}<select value={action.unit} onChange={e => updateAction(index, { ...action, unit: e.target.value as "minutes" | "hours" | "days" })}>{(["minutes", "hours", "days"] as const).map(unit => <option key={unit} value={unit}>{t(`automations.${unit}`)}</option>)}</select></label></div>}
          {action.type === "http_request" && <>
            <div className="form-grid"><label>{t("automations.method")}<select value={action.method} onChange={e => updateAction(index, { ...action, method: e.target.value as typeof action.method })}>{["GET", "POST", "PUT", "PATCH"].map(method => <option key={method}>{method}</option>)}</select></label><label>{t("automations.url")}<input type="url" required maxLength={2048} value={action.url} onChange={e => updateAction(index, { ...action, url: e.target.value })} /></label></div>
            <div><h4>{t("automations.headers")}</h4><Pairs secret value={action.headers} onChange={headers => updateAction(index, { ...action, headers })} /><p className="field-help">{t("automations.headersHelp")}</p></div>
            <div><h4>{t("automations.query")}</h4><Pairs value={action.query} onChange={query => updateAction(index, { ...action, query })} /></div>
            {action.method !== "GET" && <label>{t("automations.body")}<textarea spellCheck={false} maxLength={16000} value={bodies[action.id] ?? JSON.stringify(action.body, null, 2)} onChange={e => setBodies(current => ({ ...current, [action.id]: e.target.value }))} /></label>}
          </>}
        </article>)}
        <button type="button" className="button secondary" disabled={draft.actions.length >= 20} onClick={() => patch({ actions: [...draft.actions, newAction(draft.trigger_type === "client_created" ? "http_request" : "send_message")] })}><Plus size={16} />{t("automations.addAction")}</button>
      </div></section>
      <div className="automation-controls"><button className="button primary" type="submit" disabled={busy || !draft.actions.length || clientsFailed}>{t(busy ? "automations.saving" : "automations.save")}</button><button type="button" className="button secondary" onClick={onClose}>{t("automations.cancel")}</button></div>
      </fieldset>
    </form>}
  </div>;
}
