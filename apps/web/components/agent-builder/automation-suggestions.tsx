"use client";
import Link from "next/link";
import { useState } from "react";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { automationTemplates, templateDraft } from "@/app/automations/templates";
import type { Automation, Draft } from "@/app/automations/types";

export function AutomationSuggestions({ ids, clientId }: { ids: string[]; clientId: string }) {
  const t = useT();
  const manualTemplates = automationTemplates.filter(item => ids.includes(item.id) && !item.unavailable && item.action !== "send_message");
  const templates = automationTemplates.filter(item => ids.includes(item.id) && !item.unavailable && item.action === "send_message");
  const [selected, setSelected] = useState(templates.map(item => item.id));
  const [messages, setMessages] = useState<Record<string, string>>(() => Object.fromEntries(templates.map(item => [item.id, t(item.category === "appointments" ? "automations.defaultMessage" : "automations.followUpMessage")])));
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  async function activate() {
    setBusy(true); setError("");
    try {
      // Existing per-business rules are reused. Refresh on every retry to avoid
      // duplicating rules created before a partial network failure.
      const existing = await api<Automation[]>("/automations");
      for (const template of templates.filter(item => selected.includes(item.id))) {
        const found = existing.find(item => item.client_id === clientId && item.template_id === template.id);
        if (found) continue;
        const draft: Draft = { ...templateDraft(template, t(`automations.catalog.${template.id}.name`), messages[template.id], ""), client_id: clientId };
        await api("/automations", { method: "POST", body: JSON.stringify(draft) });
      }
      setDone(true);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }
  if (!templates.length && !manualTemplates.length) return null;
  return <section className="builder-panel"><h2>{t("builder.automations")}</h2><p>{t("builder.automationScope")}</p>{manualTemplates.map(item => <p key={item.id}>{t(`automations.catalog.${item.id}.name`)} · <Link href="/automations">{t("builder.configure")}</Link></p>)}{done ? <p role="status">{t("builder.activated")}</p> : <fieldset disabled={busy}>{templates.map(item => <div key={item.id} className="builder-automation"><label><input type="checkbox" checked={selected.includes(item.id)} onChange={e => setSelected(e.target.checked ? [...selected, item.id] : selected.filter(id => id !== item.id))} />{t(`automations.catalog.${item.id}.name`)}</label>{selected.includes(item.id) && <textarea aria-label={t(`automations.catalog.${item.id}.name`)} value={messages[item.id]} onChange={e => setMessages({ ...messages, [item.id]: e.target.value })} maxLength={8000} rows={3} />}</div>)}<button type="button" className="button primary" disabled={!selected.length || selected.some(id => !messages[id]?.trim())} onClick={activate}>{t("builder.activate")}</button><Link className="button ghost" href="/agents">{t("builder.later")}</Link></fieldset>}{error && <p role="alert">{error}</p>}</section>;
}
