"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Cloud, Monitor } from "lucide-react";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Provider, ProviderTest } from "@/types";

const providerIds = ["ollama", "openai", "gemini", "anthropic", "groq"] as const;
const labels = { ollama: "Ollama", openai: "OpenAI", gemini: "Gemini", anthropic: "Anthropic", groq: "Groq" };
export function ModelPicker({ provider, model, onProvider, onModel, onValid, needsTools = false }: { provider: string; model: string; onProvider: (id: string) => void; onModel: (id: string) => void; onValid: (valid: boolean) => void; needsTools?: boolean }) {
  const t = useT();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [capabilities, setCapabilities] = useState<{ tools: boolean | null; vision: boolean | null } | null>(null);
  useEffect(() => { let active = true; api<Provider[]>("/providers").then(rows => { if (active) setProviders(rows); }).catch(err => { if (active) setError(messageFrom(err)); }); return () => { active = false; }; }, [revision]);
  const connection = providers.find(item => item.provider === provider);
  useEffect(() => {
    let active = true;
    setReady(false); setModels([]); setError("");
    if (connection?.configured) api<ProviderTest>(`/providers/${provider}/test`, { method: "POST" }).then(result => { if (active) { setModels(result.models); setReady(true); } }).catch(err => { if (active) setError(messageFrom(err)); });
    return () => { active = false; };
  }, [provider, connection?.configured, revision]);
  useEffect(() => {
    let active = true; setCapabilities(null);
    if ((provider === "ollama" || provider === "groq") && ready && models.includes(model)) api<{ tools: boolean | null; vision: boolean | null }>(`/providers/${provider}/capabilities?model=${encodeURIComponent(model)}`).then(result => { if (active) setCapabilities(result); }).catch(err => { if (active) setError(messageFrom(err)); });
    return () => { active = false; };
  }, [provider, model, ready, models]);
  useEffect(() => { onValid(ready && models.includes(model)); }, [ready, models, model, provider, needsTools, capabilities, onValid]);
  useEffect(() => { if (!model && ready && connection?.default_model && models.includes(connection.default_model)) onModel(connection.default_model); }, [model, ready, connection?.default_model, models, onModel]);
  return <><div className="builder-grid">{providerIds.map(id => { const item = providers.find(p => p.provider === id); return <button type="button" className="builder-card" key={id} disabled={id === "gemini"} aria-pressed={provider === id} onClick={() => { onProvider(id); onModel(""); }}>
    {id === "ollama" ? <Monitor /> : <Cloud />}<strong>{labels[id]}</strong><span>{t(id === "groq" ? "groq.description" : `builder.providerCopy.${id}`)}</span><small>{t(id === "ollama" ? "builder.local" : "builder.cloud")} · {t(id === "gemini" ? "builder.soon" : item?.configured ? id === provider && ready ? "builder.available" : "builder.configured" : "builder.disconnected")}</small></button>; })}</div>
    {connection?.configured ? <div className="builder-model"><label>{t("ollama.connection")}<input readOnly value={connection.name || connection.label} /></label>{connection.base_url && <small>{connection.base_url}</small>}<label>{t("ollama.model")}<select value={model} disabled={!ready} onChange={e => onModel(e.target.value)}><option value="">{t("builder.modelSelect")}</option>{models.map(id => <option key={id} value={id}>{id}</option>)}</select></label>{ready && models.length === 0 && <p>{t(provider === "ollama" ? "ollama.empty" : "builder.modelRequired")}</p>}
      {(provider === "ollama" || provider === "groq") && model && <><p>{t("ollama.tools")}: {t(capabilities?.tools ? "ollama.compatible" : "ollama.unknown")} · {t("ollama.vision")}: {t(capabilities?.vision ? "ollama.compatible" : "ollama.unknown")}</p>{needsTools && capabilities?.tools !== true && <p role="alert">{`${t("playground.activity.unsupported")} ${t("playground.activity.limited")}`}</p>}</>}
    </div> : <Link className="button secondary" href="/settings" target="_blank" rel="noopener noreferrer">{t("builder.connect")}</Link>}
    {provider === "groq" && <p className="field-help">{t("groq.capabilityHint")}</p>}
    <button type="button" className="button ghost" onClick={() => setRevision(n => n + 1)}>{t("builder.refresh")}</button>{error && <p role="alert">{error}</p>}
  </>;
}
