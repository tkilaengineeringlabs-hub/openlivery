"use client";
import Link from "next/link";
import { useState } from "react";
import { Modal } from "@/components/ui";
import { useLanguage } from "@/lib/i18n";
import type { AgentCatalog, BuilderContext } from "@/lib/agent-builder";
import type { Agent } from "@/types";
import { builder } from "@/lib/i18n/dicts/builder";

export function ObjectiveOptions({ catalog, value, onChange, config, onConfig, context, clientId, statuses }: {
  catalog: AgentCatalog; value: string[]; onChange: (ids: string[]) => void;
  config: Record<string, Record<string, unknown>>; onConfig: (values: Record<string, Record<string, unknown>>) => void;
  context?: BuilderContext | null; clientId?: string; statuses?: Agent["objective_status"];
}) {
  const { t, lang } = useLanguage();
  const [editing, setEditing] = useState("");
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const item = catalog.objectives.find(o => o.id === editing);
  const labels = builder[lang].objectiveFields;
  const label = (key: string) => labels[key as keyof typeof labels] || key;
  return <><h2>{t("builder.objectiveTitle")}</h2><p>{t("builder.objectiveSubtitle")}</p>{[...new Set(catalog.objectives.map(o => o.category))].map(category => <section key={category}><h3>{t(`builder.objectiveCategories.${category as keyof typeof builder.en.objectiveCategories}`)}</h3><div className="builder-grid">{catalog.objectives.filter(o => o.category === category).map(o => <article className="builder-card" key={o.id}><label className="objective-toggle"><input type="checkbox" disabled={!o.available} checked={value.includes(o.id)} onChange={e => onChange(e.target.checked ? [...value, o.id] : value.filter(id => id !== o.id))} /><strong>{o.label[lang]}</strong></label><p>{builder[lang].objectiveCopy[o.id as keyof typeof builder.en.objectiveCopy]}</p>{!o.available ? <small>{t("builder.objectiveUnavailable")}</small> : value.includes(o.id) && <><small>{t(["needs_configuration", "legacy", "paused"].includes(statuses?.[o.id]?.state || "") ? "builder.needsConfiguration" : "builder.active")}</small>{o.id === "follow_up" && <small>{String(config[o.id]?.first_minutes ?? o.default_config.first_minutes)} {t("automations.minutes")} · {String(config[o.id]?.max_attempts ?? 2)} {t("builder.attempts")}</small>}{statuses?.[o.id]?.last_run_at && <small>{t("automations.lastRun")}: {new Date(statuses[o.id].last_run_at!).toLocaleString(lang)}</small>}<button type="button" className="button secondary" onClick={() => { setEditing(o.id); setDraft({ ...o.default_config, ...config[o.id] }); }}>{t("builder.configure")}</button></>}</article>)}</div></section>)}
    <p className="builder-note">{t("builder.objectiveAuto")}</p>
    <Modal open={!!item} title={item?.label[lang] || ""} onClose={() => setEditing("")}>{item && <form className="builder-fields" onSubmit={event => { event.preventDefault(); onConfig({ ...config, [item.id]: draft }); setEditing(""); }}>
      {Object.entries(item.configuration_schema.properties).map(([key, schema]) => <label key={key}>{label(key)}{schema.type === "boolean" ? <input type="checkbox" checked={!!draft[key]} onChange={e => setDraft({ ...draft, [key]: e.target.checked })} /> : schema.type === "integer" ? <input required type="number" min={schema.minimum} max={schema.maximum} value={Number(draft[key])} onChange={e => setDraft({ ...draft, [key]: Number(e.target.value) })} /> : schema.enum ? <select value={String(draft[key])} onChange={e => setDraft({ ...draft, [key]: e.target.value })}>{schema.enum.map(option => <option key={option} value={option}>{label(option)}</option>)}</select> : schema.type === "array" && (key === "service_ids" || schema.items?.enum) ? <select multiple value={(draft[key] as string[]) || []} onChange={e => setDraft({ ...draft, [key]: Array.from(e.target.selectedOptions).map(o => o.value) })}>{(key === "service_ids" ? context?.services || [] : schema.items?.enum?.map(id => ({ id, name: label(id) })) || []).map(option => <option value={option.id} key={option.id}>{option.name}</option>)}</select> : schema.type === "array" ? <input value={((draft[key] as string[]) || []).join(", ")} onChange={e => setDraft({ ...draft, [key]: e.target.value.split(",").map(s => s.trim()).filter(Boolean) })} /> : <textarea required maxLength={8000} rows={3} value={String(draft[key] ?? "")} onChange={e => setDraft({ ...draft, [key]: e.target.value })} />}</label>)}
      <p>{t("builder.sameChannel")}</p>{item.id === "follow_up" && <p>{t("automations.noVariables")}</p>}{["appointment_reminder", "post_appointment_followup"].includes(item.id) && <p>{t("automations.variablesHelp")}</p>}{item.id.includes("appointment") && (!context?.appointments_ready || (draft.calendar === "google" && !context?.google_connected)) && <p>{t("builder.needsConfiguration")} <Link href={`/appointments?client_id=${clientId || ""}`}>{t("builder.connect")}</Link></p>}{item.id === "handoff_to_human" && <p>{t("builder.handoffLimits")}</p>}{item.id === "lead_qualification" && <p>{t("builder.leadScoring")}</p>}
      <button type="submit" className="button primary">{t("builder.save")}</button></form>}</Modal></>;
}
