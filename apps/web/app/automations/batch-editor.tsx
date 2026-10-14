"use client";
import { useState, type FormEvent } from "react";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { PageHead, Alert } from "@/components/ui";
import type { Client } from "@/types";
import { TemplateFields } from "./template-fields";
import { createBlocks, prepareBlocks } from "./selection";
import type { Draft } from "./types";

export function BatchEditor({ ids, clients, clientId, onClose, onSaved }: { ids: string[]; clients: Client[]; clientId: string; onClose: () => void; onSaved: () => void }) {
  const { t } = useLanguage();
  const [blocks, setBlocks] = useState(() => createBlocks(ids, clientId, item => t(`automations.catalog.${item.id}.name`), item => t(item.category === "appointments" ? item.id === "afterAppointment" ? "automations.completedMessage" : "automations.defaultMessage" : "automations.followUpMessage"), t("automations.keyword")));
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const block = blocks[step];
  const businessId = blocks[0]?.draft.client_id || "";
  function patch(values: Partial<Draft>) {
    setBlocks(current => current.map((item, index) => index === step ? { ...item, draft: { ...item.draft, ...values } } : item));
  }
  async function proceed(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    if (!clients.some(c => c.id === businessId)) return;
    if (step < blocks.length) {
      try { prepareBlocks(blocks); } catch { setError(t("automations.invalidJson")); return; }
      setStep(n => n + 1); return;
    }
    setBusy(true);
    try {
      await api("/automations/batch", { method: "POST", body: JSON.stringify({ items: prepareBlocks(blocks) }) });
      onSaved();
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }
  return <div className="page automations-page"><PageHead title={t(step < blocks.length ? "automations.configureSelected" : "automations.activationSummary")} description={t("automations.batchHelp")} />
    <form className="automation-form template-form" onSubmit={proceed}><fieldset className="automation-fieldset" disabled={busy}>
      <label>{t("automations.client")}<select required value={businessId} onChange={e => { const id = e.target.value; setBlocks(current => current.map(item => ({ ...item, draft: { ...item.draft, client_id: id } }))); }}><option value="">—</option>{clients.filter(c => c.is_active).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <ol className="automation-steps">{blocks.map((item, index) => <li key={item.id}><button type="button" className="button ghost" disabled={index > step} aria-current={index === step ? "step" : undefined} onClick={() => setStep(index)}>{index + 1}. {item.draft.name}</button></li>)}</ol>
      {block ? <section><h2>{block.draft.name}</h2><TemplateFields template={block.template} draft={block.draft} clients={clients} loaded failed={false} lockBusiness patch={patch} body={block.body} setBody={body => setBlocks(current => current.map((item, index) => index === step ? { ...item, body } : item))} /></section> : <section className="form-section"><div><h2>{clients.find(c => c.id === businessId)?.name}</h2><ul className="activation-summary">{blocks.map((item, index) => <li key={item.id}><strong>{item.draft.name}</strong> · {t(item.draft.enabled ? "automations.active" : "automations.inactive")} <button type="button" className="button ghost" onClick={() => setStep(index)}>{t("automations.editButton")}</button></li>)}</ul><p>{t("automations.batchHelp")}</p></div></section>}
      {error && <Alert>{error}</Alert>}<div className="automation-controls"><button type="button" className="button secondary" onClick={() => step ? setStep(n => n - 1) : window.confirm(t("automations.discard")) && onClose()}>{t("automations.back")}</button><button type="submit" className="button primary" disabled={!clients.some(c => c.id === businessId)}>{t(busy ? "automations.saving" : block ? "automations.continue" : "automations.activateCount", { count: blocks.filter(b => b.draft.enabled).length })}</button></div>
    </fieldset></form></div>;
}
