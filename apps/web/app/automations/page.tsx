"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Workflow, CalendarDays, MessageCircle, TrendingUp, Cable } from "lucide-react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { Alert, EmptyState, PageHead } from "@/components/ui";
import { TableSkeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast";
import { AutomationEditor } from "./editor";
import { TemplateEditor } from "./template-editor";
import { automationTemplates, categories, simpleTemplate, type Template } from "./templates";
import { BatchEditor } from "./batch-editor";
import { catalogTemplates, selectedTemplates, toggleSelection } from "./selection";
import type { Client } from "@/types";
import type { Automation, Draft } from "./types";
import "./automations.css";

export default function AutomationsPage() {
  const { t, lang } = useLanguage();
  const toast = useToast();
  const [clients, setClients] = useState<Client[]>([]);
  const [simple, setSimple] = useState<{ template: Template; initial: Automation | null } | null>(null);
  const [preset, setPreset] = useState<Draft | undefined>();
  const [section, setSection] = useState<"recommendedTab" | "allTab" | "mine" | "advanced">("recommendedTab");
  const [selected, setSelected] = useState<string[]>([]);
  const [clientId, setClientId] = useState("");
  const [category, setCategory] = useState("all");
  const [recommendations, setRecommendations] = useState<string[]>([]);
  const [recommendationError, setRecommendationError] = useState(false);
  const [batch, setBatch] = useState(false);
  const [items, setItems] = useState<Automation[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState<Automation | "new" | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const reload = useCallback(async () => {
    setLoading(true); setFailed(false);
    try { const [rules, businesses] = await Promise.all([api<Automation[]>("/automations"), api<Client[]>("/clients")]); setItems(rules); setClients(businesses); setClientId(current => current || (businesses.filter(c => c.is_active).length === 1 ? businesses.find(c => c.is_active)!.id : "")); }
    catch { setFailed(true); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void reload(); if (new URLSearchParams(window.location.search).get("advanced")) setSection("advanced"); const business = new URLSearchParams(window.location.search).get("client"); if (business) setClientId(business); }, [reload]);

  useEffect(() => {
    let active = true; setRecommendations([]); setRecommendationError(false);
    if (clientId) api<{ ids: string[] }>(`/automations/recommendations?client_id=${clientId}`).then(data => { if (active) setRecommendations(data.ids); }).catch(() => { if (active) setRecommendationError(true); });
    return () => { active = false; };
  }, [clientId, items]);

  async function toggle(item: Automation) {
    setBusy(item.id);
    try {
      const updated = await api<Automation>(`/automations/${item.id}/${item.enabled ? "disable" : "enable"}`, { method: "POST" });
      setItems(current => current.map(row => row.id === item.id ? updated : row));
      toast.success(t(updated.enabled ? "automations.enabled" : "automations.disabled"));
    } catch { toast.error(t("automations.error")); }
    finally { setBusy(null); }
  }
  async function remove(item: Automation) {
    if (!window.confirm(t("automations.deleteConfirm"))) return;
    setBusy(item.id);
    try {
      await api(`/automations/${item.id}`, { method: "DELETE" });
      setItems(current => current.filter(row => row.id !== item.id));
      toast.success(t("automations.deleted"));
    } catch { toast.error(t("automations.error")); }
    finally { setBusy(null); }
  }
  function origin(item: Automation) { const template = automationTemplates.find(template => template.id === item.template_id); return template ? t(`automations.catalog.${template.id}.name`) : t("automations.custom"); }
  function saved() { setBatch(false); setSelected([]); setSimple(null); setEditing(null); setPreset(undefined); setSection("mine"); void reload(); }
  function advanced() { setPreset(undefined); setEditing("new"); }
  function edit(item: Automation) { const template = simpleTemplate(item); if (template) setSimple({ template, initial: item }); else { setPreset(undefined); setEditing(item); } }
  if (batch) return <BatchEditor ids={selected} clients={clients} clientId={clientId} onClose={() => setBatch(false)} onSaved={saved} />;
  if (simple) return <TemplateEditor template={simple.template} initial={simple.initial} onClose={() => setSimple(null)} onSaved={saved} onAdvanced={(draft, id) => { setPreset(draft); setEditing(id ? items.find(item => item.id === id)! : "new"); setSimple(null); }} />;
  if (editing) return <AutomationEditor key={editing === "new" ? "new" : editing.id} initial={editing === "new" ? null : editing} preset={preset} onClose={() => setEditing(null)} onSaved={saved} />;
  const createButton = <button className="button primary" onClick={advanced}><Plus size={18} />{t("automations.advancedCreate")}</button>;
  return <div className="page automations-page">
    <PageHead title={t("builder.customFlows")} description={t("automations.multiDescription")} />
    <div className="tabs">{(["recommendedTab", "allTab", "mine", "advanced"] as const).map(tab => <button key={tab} aria-pressed={section === tab} className={section === tab ? "active" : ""} onClick={() => setSection(tab)}>{t(`automations.${tab}`)}</button>)}</div>
    {(section === "recommendedTab" || section === "allTab") && <>
      <div className="automation-catalog-filters"><label>{t("automations.client")}<select value={clientId} onChange={e => setClientId(e.target.value)}><option value="">{t("automations.selectBusiness")}</option>{clients.filter(c => c.is_active).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>{t("automations.category")}<select value={category} onChange={e => setCategory(e.target.value)}><option value="all">{t("automations.allTab")}</option>{categories.map(id => <option key={id} value={id}>{t(`automations.categories.${id}`)}</option>)}</select></label></div>
      {failed && <Alert>{t("automations.loadError")} <button className="button secondary" onClick={() => void reload()}>{t("automations.retry")}</button></Alert>}
      {recommendationError && section === "recommendedTab" && <Alert>{t("automations.loadError")}</Alert>}
      {section === "recommendedTab" && !clientId && <p>{t("automations.chooseBusinessRecommendations")}</p>}
      {section === "recommendedTab" && clientId && !recommendations.length && !recommendationError && <p>{t("automations.noRecommendations")}</p>}
      <div className="template-catalog">{categories.map(group => {
        const templates = catalogTemplates(section === "recommendedTab", recommendations, category).filter(item => item.category === group);
        if (!templates.length) return null;
        const Icon = { appointments: CalendarDays, sales: TrendingUp, care: MessageCircle, integrations: Cable }[group];
        return <section key={group}><h2 className="template-category">{t(`automations.categories.${group}`)}</h2><div className="template-grid">{templates.map(template => <label key={template.id} className={`template-card selectable ${selected.includes(template.id) ? "selected" : ""} ${template.unavailable ? "unavailable" : ""}`}><div className="template-card-top"><span className="template-icon"><Icon size={20} /></span><input type="checkbox" disabled={template.unavailable} checked={selected.includes(template.id)} onChange={() => setSelected(ids => toggleSelection(ids, template.id))} aria-label={t(`automations.catalog.${template.id}.name`)} /></div><small>{t(`automations.categories.${group}`)}</small><h3>{t(`automations.catalog.${template.id}.name`)}</h3><p>{t(`automations.catalog.${template.id}.description`)}</p>{template.unavailable ? <span className="template-badge muted">{t("automations.comingSoon")}</span> : recommendations.includes(template.id) ? <span className="template-badge">{t("automations.forBusiness")}</span> : template.action === "http_request" ? <span className="template-badge muted">{t("automations.requiresIntegration")}</span> : template.badge && <span className="template-badge">{t(`automations.${template.badge}`)}</span>}</label>)}</div></section>;
      })}</div>
      <div className="automation-selection-bar"><strong aria-live="polite">{t("automations.selectedCount", { count: selectedTemplates(selected).length })}</strong><div className="automation-controls"><button className="button secondary" disabled={!selected.length} onClick={() => setSelected([])}>{t("automations.clear")}</button><button className="button primary" disabled={!selected.length || loading || failed} onClick={() => setBatch(true)}>{t("automations.configureSelected")}</button></div></div>
    </>}
    {section === "advanced" && <section className="form-section"><div><h2>{t("automations.advanced")}</h2><p>{t("automations.advancedHelp")}</p></div>{createButton}</section>}
    {section === "mine" && (loading ? <TableSkeleton columns={5} /> : failed ? <Alert>{t("automations.loadError")} <button className="button secondary" onClick={() => void reload()}>{t("automations.retry")}</button></Alert> : items.length === 0 ?
      <EmptyState icon={<Workflow />} title={t("automations.empty")} description={t("automations.emptyDescription")} action={createButton} /> :
      <div className="automation-list">{items.map(item => <article className="form-section automation-summary" key={item.id}>
        <div><h2>{item.name}</h2><p>{item.client_id ? clients.find(client => client.id === item.client_id)?.name ?? t("automations.businessUnavailable") : t("automations.allClients")} · {origin(item)}{item.template_id && automationTemplates.find(t => t.id === item.template_id) ? ` · ${t(`automations.categories.${automationTemplates.find(t => t.id === item.template_id)!.category}`)}` : ""}</p>
          {item.template_id && !simpleTemplate(item) && <p className="field-help">{t("automations.unsupportedEdit")}</p>}
          <small>{t("automations.lastRun")}: {item.last_run_at ? new Date(item.last_run_at).toLocaleString(lang) : t("automations.never")}{item.last_run_status ? ` · ${t(`automations.status.${item.last_run_status}`)}` : ""}</small></div>
        <div className="automation-controls"><span className={`status ${item.enabled ? "status-active" : "status-inactive"}`}>{t(item.enabled ? "automations.active" : "automations.inactive")}</span>
          <button className="button secondary" disabled={busy !== null} onClick={() => void toggle(item)}>{t(item.enabled ? "automations.disable" : "automations.enable")}</button>
          <button className="button secondary" disabled={busy !== null} onClick={() => edit(item)}>{t("automations.editButton")}</button>
          <button className="button ghost danger" disabled={busy !== null} onClick={() => void remove(item)}>{t("automations.delete")}</button>
        </div>
      </article>)}</div>)}
  </div>;
}
