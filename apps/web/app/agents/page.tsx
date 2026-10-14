"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Bot, Plus, Search } from "lucide-react";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { businessLabel, useIndustries } from "@/lib/industries";
import { EmptyState, PageHead, StatusBadge } from "@/components/ui";
import { TableSkeleton } from "@/components/skeleton";
import { providerLabel } from "@/lib/providers";
import type { AgentCatalog } from "@/lib/agent-builder";
import { effectiveTools } from "@/components/agent-builder/detail-panels";
import { channelName } from "@/components/agent-builder/choices";
import "@/components/agent-builder/builder.css";
import type { Agent, Client } from "@/types";

export default function AgentsPage() {
  const { t, lang } = useLanguage();
  const catalog = useIndustries();
  const [definitions, setDefinitions] = useState<AgentCatalog | null>(null);
  const [error, setError] = useState("");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [clientId, setClientId] = useState("");
  const [search, setSearch] = useState("");
  const [loaded, setLoaded] = useState(false);
  useEffect(() => { Promise.all([api<Agent[]>("/agents"), api<Client[]>("/clients"), api<AgentCatalog>("/catalog/agent-configuration")]).then(([a, c, d]) => { setAgents(a); setClients(c); setDefinitions(d); }).catch(err => setError(messageFrom(err))).finally(() => setLoaded(true)); }, []);
  const visible = useMemo(() => agents.filter((agent) => (!clientId || agent.client_id === clientId) && `${agent.name} ${agent.client.name}`.toLowerCase().includes(search.toLowerCase())), [agents, clientId, search]);
  return <div className="page"><PageHead eyebrow={t("agents.list.eyebrow")} title={t("agents.list.title")} description={t("agents.list.description")} action={<Link href="/agents/new" className="button primary"><Plus size={18} /> {t("agents.list.newAgent")}</Link>} />
    <Link className="button secondary" href="/agents/templates">{t("builder.library")}</Link>
    <div className="toolbar filters"><label className="search-box"><Search size={18} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("agents.list.searchPlaceholder")} /></label><label className="filter-select">{t("agents.list.clientLabel")}<select value={clientId} onChange={(e) => setClientId(e.target.value)}><option value="">{t("agents.list.allClients")}</option>{clients.map((client) => <option value={client.id} key={client.id}>{client.name}</option>)}</select></label></div>
    {error && <p role="alert">{error}</p>}
    {!loaded ? <TableSkeleton columns={5} /> : visible.length ? <div className="builder-grid">{visible.map(agent => {
      const objectives = agent.objectives?.map(id => definitions?.objectives.find(item => item.id === id)?.label[lang]).filter(Boolean).join(" · ") || t("builder.custom");
      const tools = [...effectiveTools(agent).map(id => definitions?.tools.find(item => item.id === id)?.label[lang]), ...(agent.custom_tool_names || [])].filter(Boolean).join(" · ") || t("builder.none");
      return <article key={agent.id} className="builder-card"><Link href={`/agents/${agent.id}`} className="entity-cell"><span className="agent-avatar"><Bot size={18} /></span><strong>{agent.name}</strong></Link><Link href={`/clients/${agent.client_id}`} className="table-link">{agent.client.name}</Link><small>{businessLabel(catalog, agent.client, lang)}</small><StatusBadge active={agent.is_active} /><dl className="agent-card-details"><dt>{t("builder.steps.objectives")}</dt><dd>{objectives}</dd><dt>{t("builder.steps.model")}</dt><dd>{agent.model ? `${providerLabel(agent.provider)} · ${agent.model}` : t("agents.list.notConfigured")}</dd><dt>{t("builder.selectedChannels")}</dt><dd>{agent.selected_channels?.map(channelName).join(" · ") || t("builder.none")}</dd><dt>{t("builder.linkedChannels")}</dt><dd>{agent.channel_types?.map(channelName).join(" · ") || t("builder.none")}</dd><dt>{t("builder.steps.tools")}</dt><dd>{tools}</dd></dl><Link href={`/agents/${agent.id}`} className="button ghost">{t("builder.view")} <ArrowRight size={17} /></Link></article>;
    })}</div> : !error && <EmptyState icon={<Bot />} title={t(agents.length ? "builder.noMatches" : "builder.emptyTitle")} description={t("builder.emptyCopy")} action={<Link href="/agents/new" className="button primary">{t("builder.emptyButton")}</Link>} />}
  </div>;
}
