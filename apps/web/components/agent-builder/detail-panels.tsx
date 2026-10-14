"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { appointmentTools, tones, type AgentCatalog, type BuilderContext } from "@/lib/agent-builder";
import { providerLabel } from "@/lib/providers";
import type { Agent } from "@/types";
import { ChannelChoices, channelName, ToolChoices } from "./choices";
import { ModelPicker } from "./model-picker";
import { ObjectiveOptions } from "./objective-options";

export type BuilderTab = "summary" | "objectives" | "model" | "channels" | "permissions";
export function effectiveTools(agent: Agent) {
  if (agent.objectives_managed) return agent.selected_tools || [];
  return [...(agent.knowledge_enabled ? ["knowledge"] : []), ...(agent.appointments_enabled ? appointmentTools : []), ...(agent.escalation_builtin_enabled ? ["escalate_to_human"] : [])];
}
export function DetailPanel({ agent, tab, onSaved }: { agent: Agent; tab: BuilderTab; onSaved: () => Promise<void> }) {
  const { t, lang } = useLanguage();
  const [catalog, setCatalog] = useState<AgentCatalog | null>(null);
  const [context, setContext] = useState<BuilderContext | null>(null);
  const [objectiveConfig, setObjectiveConfig] = useState(agent.objective_config || {});
  const [objectives, setObjectives] = useState(agent.objectives || []);
  const [channels, setChannels] = useState(agent.selected_channels || []);
  const [tools, setTools] = useState(effectiveTools(agent));
  const [shared, setShared] = useState(agent.shared_tool_ids || []);
  const [provider, setProvider] = useState(agent.provider);
  const [model, setModel] = useState(agent.model);
  const [modelValid, setModelValid] = useState(false);
  const [tone, setTone] = useState(agent.tone || "");
  const [personality, setPersonality] = useState(agent.personality);
  const [welcome, setWelcome] = useState(agent.welcome_message || "");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [replacement, setReplacement] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    Promise.all([api<AgentCatalog>(`/catalog/agent-configuration?language=${lang}`), api<BuilderContext>(`/catalog/agent-configuration/${agent.client_id}`)]).then(([defs, ctx]) => {
      if (active) { setCatalog(defs); setContext({ ...ctx, tools: ctx.tools.filter(tool => tool.agent_id !== agent.id) }); }
    }).catch(err => { if (active) setError(messageFrom(err)); });
    return () => { active = false; };
  }, [agent.id, agent.client_id, revision, lang]);
  async function save(values: Record<string, unknown>) {
    setBusy(true); setError(""); setNotice("");
    try { await api(`/agents/${agent.id}`, { method: "PATCH", body: JSON.stringify(values) }); await onSaved(); setNotice(t("agents.detail.configSaved")); }
    catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }
  if (!catalog) return <section className="builder-panel"><p>{error || t("builder.loading")}</p><button className="button secondary" onClick={() => setRevision(n => n + 1)}>{t("builder.retry")}</button></section>;
  const template = agent.template_snapshot || catalog.templates.find(item => item.id === agent.template_id);
  const objectiveNames = (agent.objectives || []).map(id => catalog.objectives.find(item => item.id === id)?.label[lang]).filter(Boolean).join(" · ") || t("builder.custom");
  const toolNames = [...effectiveTools(agent).map(id => catalog.tools.find(item => item.id === id)?.label[lang]), ...(agent.custom_tool_names || [])].filter(Boolean).join(" · ") || t("builder.none");
  return <section className="builder-panel builder-page"><fieldset disabled={busy}>
    {tab === "summary" && <><h2>{t("builder.summary")}</h2><dl className="builder-summary"><dt>{t("builder.steps.business")}</dt><dd>{agent.client.name}</dd><dt>{t("builder.steps.objectives")}</dt><dd>{objectiveNames}</dd><dt>{t("builder.steps.model")}</dt><dd>{providerLabel(agent.provider)} · {agent.model}</dd><dt>{t("builder.basedOn")}</dt><dd>{template?.name[lang] || t("builder.custom")}{agent.template_version ? ` · v${agent.template_version}` : ""}</dd><dt>{t("builder.selectedChannels")}</dt><dd>{agent.selected_channels?.map(channelName).join(" · ") || t("builder.none")}</dd><dt>{t("builder.linkedChannels")}</dt><dd>{agent.channel_types?.map(channelName).join(" · ") || t("builder.none")}</dd><dt>{t("builder.steps.tools")}</dt><dd>{toolNames}</dd></dl><div className="builder-fields"><label>{t("builder.changeTemplate")}<select value={replacement} onChange={e => setReplacement(e.target.value)}><option value="">{t("builder.custom")}</option>{catalog.templates.filter(item => item.active).map(item => <option key={item.id} value={item.id}>{item.name[lang]}</option>)}</select></label><button type="button" className="button secondary" disabled={!replacement} onClick={async () => { if (!window.confirm(t("builder.confirmTemplate"))) return; try { const item = await api<import("@/lib/agent-builder").TemplatePreview>(`/catalog/agent-templates/${agent.client_id}/${replacement}/preview?language=${agent.prompt_language}`); await save({ ...item.defaults, apply_template: true }); setObjectives(item.defaults.objectives); setObjectiveConfig(item.defaults.objective_config || {}); setTools(item.defaults.selected_tools); setChannels(item.defaults.selected_channels); setTone(item.defaults.tone); setReplacement(""); } catch (err) { setError(messageFrom(err)); } }}>{t("builder.applyTemplate")}</button><label>{t("builder.tone")}<select value={tone} onChange={e => setTone(e.target.value)}><option value="">{t("builder.custom")}</option>{tones.map(id => <option key={id} value={id}>{t(`builder.tones.${id}`)}</option>)}</select></label><label>{t("builder.personality")}<textarea value={personality} onChange={e => setPersonality(e.target.value)} rows={3} /></label><label>{t("builder.welcome")}<textarea value={welcome} maxLength={2000} onChange={e => setWelcome(e.target.value)} rows={3} /></label><small>{t("builder.welcomeHelp")}</small></div><button className="button primary" onClick={() => save({ tone, personality, welcome_message: welcome })}>{t("builder.save")}</button></>}
    {tab === "objectives" && <><ObjectiveOptions catalog={catalog} value={objectives} onChange={setObjectives} config={objectiveConfig} onConfig={setObjectiveConfig} context={context} clientId={agent.client_id} statuses={agent.objective_status} /><p className="builder-note">{t("builder.suggested")}</p><button className="button primary" onClick={() => save({ objectives, objective_config: objectiveConfig })}>{t("builder.save")}</button></>}
    {tab === "model" && <><ModelPicker provider={provider} model={model} onProvider={setProvider} onModel={setModel} onValid={setModelValid} needsTools={agent.appointments_enabled || agent.escalation_builtin_enabled || !!agent.custom_tool_names?.length} /><button className="button primary" disabled={!modelValid} onClick={() => save({ provider, model, apply_builder: true })}>{t("builder.save")}</button></>}
    {tab === "channels" && <><ChannelChoices catalog={catalog} value={channels} onChange={setChannels} /><p>{t("builder.linkedChannels")}: {agent.channel_types?.map(channelName).join(" · ") || t("builder.none")}</p><div className="builder-actions"><button className="button primary" onClick={() => save({ selected_channels: channels })}>{t("builder.save")}</button><Link className="button secondary" href={`/clients/${agent.client_id}`}>{t("builder.connect")}</Link></div></>}
    {tab === "permissions" && <><ToolChoices managed={agent.objectives_managed} context={context} clientId={agent.client_id} value={tools} shared={shared} onChange={setTools} onShared={setShared} /><button className="button ghost" onClick={() => setRevision(n => n + 1)}>{t("builder.refresh")}</button><button className="button primary" onClick={() => save({ selected_tools: tools, shared_tool_ids: shared })}>{t("builder.save")}</button></>}

    </fieldset>{error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </section>;
}
