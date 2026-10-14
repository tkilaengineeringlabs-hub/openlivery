"use client";
import { useLanguage } from "@/lib/i18n";
import { Alert } from "@/components/ui";
import type { Client } from "@/types";
import { Pairs } from "./editor";
import type { Template } from "./templates";
import { inactivityMinutes, upcomingMinutes, triggers, type Draft, type Trigger } from "./types";

export function TemplateFields({ template, draft, clients, loaded, failed, patch, body, setBody, lockBusiness = false }: {
  template: Template; draft: Draft; clients: Client[]; loaded: boolean; failed: boolean;
  patch: (values: Partial<Draft>) => void; body: string; setBody: (value: string) => void; lockBusiness?: boolean;
}) {
  const { t } = useLanguage();
  const action = draft.actions[0];
  const appointments = draft.trigger_type.startsWith("appointment_");
  return (
      <section className="form-section"><div className="form-fields">
        <label>{t("automations.name")}<input required maxLength={180} value={draft.name} onChange={e => patch({ name: e.target.value })} /></label>
        <label>{t("automations.client")}<select required disabled={lockBusiness || !loaded || failed} value={draft.client_id || ""} onChange={e => patch({ client_id: e.target.value })}><option value="">—</option>{clients.map(client => <option key={client.id} value={client.id}>{client.name}</option>)}</select></label>
        {failed && <Alert>{t("automations.loadError")}</Alert>}
        {template.fields.includes("http") && <label>{t("automations.event")}<select value={draft.trigger_type} onChange={e => { const trigger = e.target.value as Trigger; patch({ trigger_type: trigger, trigger_config: ["appointment_upcoming", "conversation_inactive"].includes(trigger) ? { minutes: 30 } : {} }); }}>{triggers.map(trigger => <option key={trigger} value={trigger}>{t(`automations.trigger.${trigger}`)}</option>)}</select></label>}
        {["appointment_upcoming", "conversation_inactive"].includes(draft.trigger_type) && <label>{t(appointments ? "automations.beforeAppointment" : "automations.duration")}<select value={draft.trigger_config.minutes} onChange={e => patch({ trigger_config: { minutes: Number(e.target.value) } })}>{(appointments ? upcomingMinutes : inactivityMinutes).map(minutes => <option key={minutes} value={minutes}>{minutes < 60 ? minutes : minutes / 60} {t(minutes < 60 ? "automations.minutes" : "automations.hours")}</option>)}</select></label>}
        {draft.trigger_type === "conversation_inactive" && <p className="field-help">{t("automations.inactivityHelp")}</p>}
        {template.fields.includes("keyword") && <label>{t("automations.keywordLabel")}<input required maxLength={2000} value={draft.conditions[0].value} onChange={e => patch({ conditions: [{ field: "message.text", operator: "contains", value: e.target.value }] })} /></label>}
        {action.type === "handoff_to_human" && <><label>{t("automations.handoffDestination")}<input readOnly value="Inbox" /></label><p className="field-help">{t("automations.handoffScope")}</p></>}
        {action.type === "send_message" && <>
          <label>{t("automations.channel")}<input readOnly value={t("automations.linkedChannel")} /></label>
          <p className="field-help">{t("automations.channelHelp")}</p>
          <label>{t("automations.message")}<textarea required maxLength={8000} rows={5} value={action.text} onChange={e => patch({ actions: [{ ...action, text: e.target.value }] })} /></label>
          <p className="field-help">{t(appointments ? "automations.variablesHelp" : "automations.noVariables")}</p>
          {appointments && <p className="field-help">{t("automations.appointmentHelp")}</p>}
        </>}
        {action.type === "http_request" && <>
          <label>{t("automations.url")}<input required type="url" maxLength={2048} value={action.url} onChange={e => patch({ actions: [{ ...action, url: e.target.value }] })} /></label>
          <label>{t("automations.method")}<select value={action.method} onChange={e => patch({ actions: [{ ...action, method: e.target.value as typeof action.method }] })}>{["GET", "POST", "PUT", "PATCH"].map(method => <option key={method}>{method}</option>)}</select></label>
          <details><summary>{t("automations.headers")}</summary><Pairs secret value={action.headers} onChange={headers => patch({ actions: [{ ...action, headers }] })} /><p className="field-help">{t("automations.headersHelp")}</p></details>
          <p className="field-help">{t("automations.httpHelp")}</p>
          <label>{t("automations.dataToSend")}<textarea spellCheck={false} rows={5} maxLength={16000} value={body} onChange={e => { setBody(e.target.value); }} /></label>
        </>}
        <label>{t("automations.state")}<select value={draft.enabled ? "active" : "paused"} onChange={e => patch({ enabled: e.target.value === "active" })}><option value="active">{t("automations.active")}</option><option value="paused">{t("automations.inactive")}</option></select></label>
      </div></section>
  );
}
