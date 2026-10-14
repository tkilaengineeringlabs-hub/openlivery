"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Building2, Check, Sparkles } from "lucide-react";
import { api, messageFrom } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { businessLabel, useIndustries } from "@/lib/industries";
import { PageHead } from "@/components/ui";
import { ChatPlayground } from "@/components/chat-playground";
import { providerLabel } from "@/lib/providers";
import { appointmentTools, tones, type AgentCatalog, type BuilderContext, type Tone, type TemplateMatch, type TemplatePreview as Preview } from "@/lib/agent-builder";
import type { Agent, Client } from "@/types";
import { ChannelChoices, channelName, ToolChoices } from "./choices";
import { ModelPicker } from "./model-picker";
import { TemplatePreview } from "./template-preview";
import { ObjectiveOptions } from "./objective-options";

const steps = ["business", "objectives", "channels", "tools", "model", "template", "personalize", "summary"] as const;
export function AgentBuilder() {
  const { t, lang } = useLanguage();
  const industries = useIndustries();
  const [clients, setClients] = useState<Client[]>([]);
  const [catalog, setCatalog] = useState<AgentCatalog | null>(null);
  const [context, setContext] = useState<BuilderContext | null>(null);
  const [loadRevision, setLoadRevision] = useState(0);
  const [contextRevision, setContextRevision] = useState(0);
  const [error, setError] = useState("");
  const [step, setStep] = useState(0);
  const [clientId, setClientId] = useState("");
  const [objectiveConfig, setObjectiveConfig] = useState<Record<string, Record<string, unknown>>>({});
  const [objectives, setObjectives] = useState<string[]>([]);
  const [channels, setChannels] = useState<string[]>([]);
  const [tools, setTools] = useState<string[]>([]);
  const [shared, setShared] = useState<string[]>([]);
  const [provider, setProvider] = useState("ollama");
  const [model, setModel] = useState("");
  const [permissionsValid, setPermissionsValid] = useState(false);
  const [modelValid, setModelValid] = useState(false);
  const [matches, setMatches] = useState<TemplateMatch[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [templateBusy, setTemplateBusy] = useState(false);
  const [templateId, setTemplateId] = useState("");
  const [name, setName] = useState("");
  const [tone, setTone] = useState<Tone>("friendly");
  const [personality, setPersonality] = useState("");
  const [welcome, setWelcome] = useState("");
  const [instructions, setInstructions] = useState("");
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(2048);
  const [memory, setMemory] = useState(30);
  const [active, setActive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<Agent | null>(null);
  const [testing, setTesting] = useState(false);
  useEffect(() => {
    let active = true; setError("");
    Promise.all([api<Client[]>("/clients"), api<AgentCatalog>(`/catalog/agent-configuration?language=${lang}`)]).then(([items, definitions]) => {
      if (!active) return;
      const usable = items.filter(item => item.is_active);
      setClients(usable); setCatalog(definitions);
      const preferred = new URLSearchParams(window.location.search).get("client");
      if (usable.length === 1) setClientId(usable[0].id);
      else if (preferred && usable.some(item => item.id === preferred)) setClientId(preferred);
    }).catch(err => { if (active) setError(messageFrom(err)); });
    return () => { active = false; };
  }, [loadRevision, lang]);
  useEffect(() => {
    let active = true; setContext(null);
    if (clientId) api<BuilderContext>(`/catalog/agent-configuration/${clientId}`).then(item => { if (active) setContext(item); }).catch(err => { if (active) setError(messageFrom(err)); });
    return () => { active = false; };
  }, [clientId, contextRevision]);
  useEffect(() => {
    let active = true; setPermissionsValid(false);
    if (!clientId) return;
    api<{ selected_tools: string[] }>(`/catalog/objective-configuration/${clientId}`, { method: "POST", body: JSON.stringify({ objectives, objective_config: objectiveConfig, language: lang }) }).then(data => { if (active) { setTools(data.selected_tools); setPermissionsValid(true); } }).catch(err => { if (active) setError(messageFrom(err)); });
    return () => { active = false; };
  }, [clientId, objectives, objectiveConfig, lang, contextRevision]);
  const business = clients.find(item => item.id === clientId);
  const template = catalog?.templates.find(item => item.id === templateId);
  const recommendedTools = [...new Set(catalog?.objectives.filter(item => objectives.includes(item.id)).flatMap(item => item.recommended_tools) || [])];
  const templates = matches.map(item => item.template);
  useEffect(() => {
    let active = true;
    if (!clientId) return;
    api<TemplateMatch[]>(`/catalog/agent-templates/${clientId}/recommendations`, { method: "POST", body: JSON.stringify({ objectives, channels }) }).then(items => { if (active) setMatches(items); }).catch(err => { if (active) setError(messageFrom(err)); });
    return () => { active = false; };
  }, [clientId, objectives, channels, contextRevision]);
  useEffect(() => {
    let active = true;
    const preferred = new URLSearchParams(window.location.search).get("template");
    if (!clientId || !preferred) return;
    api<Preview>(`/catalog/agent-templates/${clientId}/${encodeURIComponent(preferred)}/preview?language=${lang}`).then(item => { if (active) { setPreview(item); setStep(5); } }).catch(err => { if (active) setError(messageFrom(err)); });
    return () => { active = false; };
  }, [clientId, lang]);
  async function chooseTemplate(id: string) {
    setTemplateBusy(true); setError("");
    try { setPreview(await api<Preview>(`/catalog/agent-templates/${clientId}/${id}/preview?language=${lang}`)); }
    catch (err) { setError(messageFrom(err)); } finally { setTemplateBusy(false); }
  }
  function applyPreview() {
    if (!preview || (templateId && !window.confirm(t("builder.confirmTemplate")))) return;
    const values = preview.defaults;
    setTemplateId(values.template_id); setObjectiveConfig(values.objective_config || {}); setObjectives(values.objectives); setTools(values.selected_tools); setChannels(values.selected_channels);
    setTone(values.tone); setInstructions(values.instructions); setName(values.name); setStep(6);
  }
  const appointmentGoals = objectives.some(id => ["book_appointment", "reschedule_appointment", "cancel_appointment"].includes(id));
  const appointmentSelected = appointmentTools.every(id => tools.includes(id));
  const nextAllowed = step === 0 ? !!business : step === 1 ? objectives.length > 0 && permissionsValid : step === 4 ? modelValid : step === 6 ? !!name.trim() : true;
  const objectiveNames = (ids: string[]) => ids.map(id => catalog?.objectives.find(item => item.id === id)?.label[lang]).filter(Boolean).join(" · ") || t("builder.none");
  const toolNames = (ids: string[]) => ids.map(id => catalog?.tools.find(item => item.id === id)?.label[lang]).filter(Boolean).join(" · ") || t("builder.none");


  async function create() {
    if (!business || !modelValid || !name.trim() || busy) return;
    setBusy(true); setError("");
    try {
      const item = await api<Agent>("/agents", { method: "POST", body: JSON.stringify({
        apply_builder: true, client_id: clientId, name: name.trim(), objectives, objective_config: objectiveConfig, selected_channels: channels,
        selected_tools: tools, shared_tool_ids: shared, provider, model, template_id: templateId || null,
        tone, personality, welcome_message: welcome, instructions, prompt_language: lang,
        timezone: business.timezone || "UTC", temperature, max_tokens: maxTokens, memory_limit: memory,
        is_active: active, image_enabled: false, audio_enabled: false,
      }) });
      setCreated(item);
    } catch (err) { setError(messageFrom(err)); } finally { setBusy(false); }
  }
  if (created) return <div className="page builder-page"><PageHead title={t("builder.ready")} description={t("builder.persisted")} /><section className="builder-panel"><h2>{created.name}</h2><p>{created.client.name} · {providerLabel(created.provider)} · {created.model}</p><ul className="builder-success">{(["modelDone", "toolsDone", "channelsDone", "goalsDone"] as const).map(key => <li key={key}><Check size={18} />{t(`builder.${key}`)}</li>)}</ul><div className="builder-actions"><button type="button" className="button primary" onClick={() => setTesting(true)}>{t("builder.test")}</button><Link className="button secondary" href={`/agents/${created.id}`}>{t("builder.view")}</Link></div></section>{testing && <section className="builder-panel"><p className="builder-note">{t("builder.playgroundNotice")}</p><ChatPlayground lockedAgentId={created.id} /></section>}</div>;
  if (!catalog) return <div className="page builder-page"><h1>{t("builder.title")}</h1>{error ? <><p role="alert">{error}</p><button className="button secondary" onClick={() => setLoadRevision(n => n + 1)}>{t("builder.retry")}</button></> : <p>{t("builder.loading")}</p>}</div>;
  return <div className="page builder-page"><PageHead title={t("builder.title")} description={t("builder.subtitle")} />
    <ol className="builder-stepper">{steps.map((id, index) => <li key={id}><button type="button" disabled={busy || templateBusy || index > step} aria-current={index === step ? "step" : undefined} onClick={() => setStep(index)}>{index + 1}. {t(`builder.steps.${id}`)}</button></li>)}</ol>
    <section className="builder-panel"><h2>{t(`builder.questions.${steps[step]}`)}</h2>
      {step === 0 && (clients.length ? <div className="builder-grid">{clients.map(item => <button type="button" className="builder-card" key={item.id} aria-pressed={clientId === item.id} onClick={() => { if (clientId !== item.id) { setClientId(item.id); setTools([]); setShared([]); setTemplateId(""); setPreview(null); setMatches([]); } }}>{item.logo_url ? <img src={item.logo_url} alt="" /> : <Building2 />}<strong>{item.name}</strong><span>{industries.find(industry => industry.code === item.industry)?.label[lang]}</span><small>{businessLabel(industries, item, lang)}</small></button>)}</div> : <><p>{t("builder.noBusiness")}</p><Link href="/clients/new" className="button primary">{t("builder.addBusiness")}</Link></>)}
      {step === 0 && business && !!matches.length && <aside className="builder-note"><h3>{t("builder.recommendedBusiness")}</h3><div className="builder-grid">{matches.filter(item => item.recommended).slice(0, 3).map(({template: item}) => <button type="button" className="builder-card" key={item.id} onClick={() => { chooseTemplate(item.id); setStep(5); }}><strong>{item.name[lang]}</strong><span>{item.description[lang]}</span></button>)}</div></aside>}
      {step === 1 && <><ObjectiveOptions catalog={catalog} value={objectives} onChange={setObjectives} config={objectiveConfig} onConfig={setObjectiveConfig} context={context} clientId={clientId} />{!!objectives.length && <aside className="builder-note"><strong>{t("builder.suggested")}</strong><p>{toolNames(recommendedTools)}</p><p>{templates[0]?.name[lang]} · {templates[0]?.recommended_channels.map(channelName).join(" · ")}</p></aside>}</>}
      {step === 2 && <ChannelChoices catalog={catalog} value={channels} onChange={setChannels} />}
      {step === 3 && <><ToolChoices managed context={context} clientId={clientId} value={tools} shared={shared} onChange={setTools} onShared={setShared} /><button type="button" className="button ghost" onClick={() => setContextRevision(n => n + 1)}>{t("builder.refresh")}</button>{appointmentGoals && !appointmentSelected && <p className="builder-note">{t("builder.missingCalendar")}</p>}</>}
      {step === 4 && <><ModelPicker provider={provider} model={model} onProvider={setProvider} onModel={setModel} onValid={setModelValid} needsTools={tools.length > 0 || shared.length > 0} />{!modelValid && <p>{t("builder.modelRequired")}</p>}</>}
      {step === 5 && <><h3>{t("builder.recommendedBusiness")}</h3>{!matches.some(item => item.exact_match) && <p>{t("builder.noExact")}</p>}{([true, false] as const).map(recommended => <div key={String(recommended)}><h4>{t(recommended ? "builder.recommended" : "builder.allTemplates")}</h4><div className="builder-grid">{matches.filter(item => item.recommended === recommended).map(({ template: item, score, reasons }) => <button type="button" disabled={templateBusy} className="builder-card" aria-pressed={preview?.template.id === item.id} key={item.id} onClick={() => chooseTemplate(item.id)}><Sparkles /><strong>{item.name[lang]}</strong><span>{item.description[lang]}</span><span>{objectiveNames(item.objectives)}</span><small>{score} · {Object.entries(reasons).filter(([,value]) => value > 0).map(([key, value]) => `${t(key === "business_type" || key === "industry" ? "builder.steps.business" : key === "objectives" ? "builder.steps.objectives" : key === "tools" ? "builder.steps.tools" : "builder.steps.channels")}: ${value}`).join(" · ")}</small></button>)}</div></div>)}<button type="button" className="button secondary" onClick={() => { setTemplateId(""); setPreview(null); }}>{t("builder.scratch")}</button>{preview && <><TemplatePreview preview={preview} catalog={catalog} clientId={clientId} /><button type="button" className="button primary" onClick={applyPreview}>{t("builder.applyTemplate")}</button></>}</>}
      {step === 6 && <div className="builder-fields"><label>{t("builder.name")}<input required maxLength={180} value={name} onChange={e => setName(e.target.value)} placeholder={t("builder.namePlaceholder")} /></label><label>{t("builder.tone")}<select value={tone} onChange={e => setTone(e.target.value as Tone)}>{tones.map(id => <option key={id} value={id}>{t(`builder.tones.${id}`)}</option>)}</select></label><label>{t("builder.personality")}<textarea rows={3} value={personality} onChange={e => setPersonality(e.target.value)} placeholder={t("builder.personalityPlaceholder")} /></label><label>{t("builder.welcome")}<textarea rows={3} maxLength={2000} value={welcome} onChange={e => setWelcome(e.target.value)} placeholder={t("builder.welcomePlaceholder")} /></label><small>{t("builder.welcomeHelp")}</small><label><input type="checkbox" checked={active} onChange={e => setActive(e.target.checked)} />{t("builder.active")}</label><details><summary>{t("builder.advanced")}</summary><div className="builder-fields"><label>{t("builder.instructions")}<textarea rows={6} value={instructions} onChange={e => setInstructions(e.target.value)} /></label><p>{t("builder.instructionsHelp")}</p><label>{t("agents.detail.temperatureLabel")}<input type="number" min={0} max={2} step={0.1} value={temperature} onChange={e => setTemperature(Number(e.target.value))} /></label><label>{t("agents.detail.maxTokensLabel")}<input type="number" min={1} max={32000} value={maxTokens} onChange={e => setMaxTokens(Number(e.target.value))} /></label><label>{t("agents.detail.memoryLimitLabel")}<input type="number" min={0} max={200} value={memory} onChange={e => setMemory(Number(e.target.value))} /></label></div></details></div>}
      {step === 7 && <><dl className="builder-summary">{[
        [t("builder.steps.business"), business?.name], [t("builder.name"), name], [t("builder.steps.objectives"), objectiveNames(objectives)],
        [t("builder.steps.channels"), channels.map(channelName).join(" · ") || t("builder.none")],
        [t("builder.steps.tools"), [toolNames(tools), ...(context?.tools.filter(item => shared.includes(item.id)).map(item => item.name) || [])].join(" · ")],
        [t("builder.steps.model"), `${providerLabel(provider)} · ${model}`], [t("builder.steps.template"), template?.name[lang] || t("builder.scratch")],
      ].map(([label, value]) => <div key={label} style={{ display: "contents" }}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><p className="builder-note">{t("builder.channelsHelp")}</p>{appointmentGoals && !appointmentSelected && <p className="builder-note">{t("builder.missingCalendar")}</p>}</>}
      {error && <p role="alert">{error}</p>}
    </section><div className="builder-actions"><button type="button" className="button secondary" disabled={step === 0 || busy} onClick={() => { setError(""); setStep(n => n - 1); }}>{t("builder.back")}</button>{step < 7 ? <button type="button" className="button primary" disabled={!nextAllowed || busy || templateBusy} onClick={() => { setError(""); setStep(n => n + 1); }}>{t("builder.next")}</button> : <button type="button" className="button primary" disabled={busy || !modelValid || !name.trim()} onClick={create}>{t(busy ? "builder.loading" : "builder.create")}</button>}</div>
  </div>;
}
