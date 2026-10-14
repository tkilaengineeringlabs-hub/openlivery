"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import type { TemplateMatch } from "@/lib/agent-builder";

export function BusinessRecommendations({ clientId, name }: { clientId: string; name: string }) {
  const { t, lang } = useLanguage();
  const [items, setItems] = useState<TemplateMatch[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<TemplateMatch[]>(`/catalog/agent-templates/${clientId}/recommendations`, { method: "POST", body: JSON.stringify({ objectives: [] }) }).then(rows => { if (active) setItems(rows.filter(item => item.recommended).slice(0, 3)); }).catch(err => { if (active) setError(messageFrom(err)); });
    return () => { active = false; };
  }, [clientId]);
  return <section className="panel"><h3>{t("builder.recommendedBusiness")} · {name}</h3>{error && <p role="alert">{error}</p>}<div className="compact-list">{items.map(({template: item}) => <Link key={item.id} className="compact-row" href={`/agents/new?client=${clientId}&template=${item.id}`}><div><strong>{item.name[lang]}</strong><small>{item.description[lang]}</small></div></Link>)}</div><Link className="button secondary" href={`/agents/new?client=${clientId}`}>{t("builder.scratch")}</Link></section>;
}
