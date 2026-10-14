"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { useIndustries } from "@/lib/industries";
import { PageHead } from "@/components/ui";
import type { AgentCatalog, TemplateMatch } from "@/lib/agent-builder";
import type { Client } from "@/types";
import "@/components/agent-builder/builder.css";

const categories = ["all", "appointments", "sales", "care", "leads", "support", "ecommerce"] as const;
export default function AgentTemplatesPage() {
  const { t, lang } = useLanguage();
  const industries = useIndustries();
  const [catalog, setCatalog] = useState<AgentCatalog | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [business, setBusiness] = useState("");
  const [matches, setMatches] = useState<TemplateMatch[]>([]);
  const [search, setSearch] = useState("");
  const [industry, setIndustry] = useState("");
  const [objective, setObjective] = useState("");
  const [category, setCategory] = useState("all");
  const [error, setError] = useState("");
  useEffect(() => { Promise.all([api<AgentCatalog>("/catalog/agent-configuration"), api<Client[]>("/clients")]).then(([defs, businesses]) => { setCatalog(defs); setClients(businesses.filter(c => c.is_active)); }).catch(err => setError(messageFrom(err))); }, []);
  useEffect(() => {
    let active = true; setMatches([]);
    if (business) api<TemplateMatch[]>(`/catalog/agent-templates/${business}/recommendations`, { method: "POST", body: JSON.stringify({ objectives: objective ? [objective] : [] }) }).then(items => { if (active) setMatches(items); }).catch(err => { if (active) setError(messageFrom(err)); });
    return () => { active = false; };
  }, [business, objective]);
  const templates = (business ? matches.map(m => m.template) : catalog?.templates || []).filter(item => item.active && (!industry || item.industry === industry) && (!objective || item.objectives.includes(objective)) && (category === "all" || item.tags.includes(category)) && [item.name.en, item.name.es, item.description.en, item.description.es, ...item.objectives.map(id => catalog?.objectives.find(o => o.id === id)?.label[lang] || "")].join(" ").toLowerCase().includes(search.toLowerCase()));
  return <div className="page builder-page"><PageHead title={t("builder.library")} description={t("builder.suggested")} action={<Link className="button secondary" href="/agents/new">{t("builder.scratch")}</Link>} />
    <div className="builder-fields"><label>{t("builder.searchTemplates")}<input value={search} onChange={e => setSearch(e.target.value)} /></label><label>{t("builder.steps.business")}<select value={business} onChange={e => setBusiness(e.target.value)}><option value="">{t("builder.all")}</option>{clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>{t("builder.industryFilter")}<select value={industry} onChange={e => setIndustry(e.target.value)}><option value="">{t("builder.all")}</option>{industries.map(i => <option key={i.code} value={i.code}>{i.label[lang]}</option>)}</select></label><label>{t("builder.objectiveFilter")}<select value={objective} onChange={e => setObjective(e.target.value)}><option value="">{t("builder.all")}</option>{catalog?.objectives.map(o => <option key={o.id} value={o.id}>{o.label[lang]}</option>)}</select></label></div>
    <div className="builder-actions">{categories.map(id => <button className="button secondary" key={id} aria-pressed={category === id} onClick={() => setCategory(id)}>{t(`builder.categories.${id}`)}</button>)}</div>
    {error && <p role="alert">{error}</p>}{!catalog && !error && <p>{t("builder.loading")}</p>}{catalog && !templates.length && <p>{t("builder.noExact")}</p>}
    <div className="builder-grid">{templates.map(item => <article className="builder-card" key={item.id}><strong>{item.name[lang]}</strong><p>{item.description[lang]}</p><small>{item.objectives.map(id => catalog?.objectives.find(o => o.id === id)?.label[lang]).join(" · ")}</small><Link className="button primary" href={`/agents/new?template=${item.id}${business ? `&client=${business}` : ""}`}>{t("builder.applyTemplate")}</Link></article>)}</div></div>;
}
