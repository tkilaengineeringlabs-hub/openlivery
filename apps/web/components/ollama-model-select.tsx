"use client";

import { useEffect, useState } from "react";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Provider } from "@/types";

type Capabilities = { tools: boolean | null; vision: boolean | null };

export function OllamaModelSelect({ value, onChange, provider = "ollama" }: { provider?: "ollama" | "groq"; value: string; onChange: (value: string) => void }) {
  const t = useT();
  const [connection, setConnection] = useState<Provider | null>(null);
  const [models, setModels] = useState<string[] | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    setBusy(true); setError(""); setModels(null);
    (async () => {
      const providers = await api<Provider[]>("/providers");
      const item = providers.find((p) => p.provider === provider);
      if (!active) return;
      setConnection(item || null);
      if (!item?.configured) throw new Error(`${provider}.not_configured`);
      const result = await api<{ models: string[] }>(`/providers/${provider}/test`, { method: "POST" });
      if (active) setModels(result.models);
    })().catch((err) => { if (active) setError(messageFrom(err)); }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [revision, provider]);

  useEffect(() => {
    if (!value && connection?.default_model && models?.includes(connection.default_model)) onChange(connection.default_model);
  }, [connection, models, value, onChange]);

  useEffect(() => {
    let active = true;
    setCapabilities(null);
    if (value && models?.includes(value)) api<Capabilities>(`/providers/${provider}/capabilities?model=${encodeURIComponent(value)}`)
      .then((result) => { if (active) setCapabilities(result); })
      .catch((err) => { if (active) setError(messageFrom(err)); });
    return () => { active = false; };
  }, [value, models, provider]);

  return <div className="form-fields">
    <label>{t("ollama.connection")}<input readOnly value={connection?.name || connection?.label || ""} /></label>
    {connection?.base_url && <p className="field-help">{connection.base_url}</p>}
    <label>{t("ollama.model")}<select required value={value} disabled={busy || !models?.length} onChange={(e) => { setError(""); onChange(e.target.value); }}>
      <option value="">{t("ollama.select")}</option>
      {value && !models?.includes(value) && <option value={value} disabled>{value}</option>}
      {(models || []).map((id) => <option key={id} value={id}>{id}</option>)}
    </select></label>
    <button type="button" className="button ghost" disabled={busy} onClick={() => setRevision((r) => r + 1)}>{t("ollama.refresh")}</button>
    {models?.length === 0 && <p>{t(provider === "groq" ? "groq.empty" : "ollama.empty")}</p>}
    {value && models && !models.includes(value) && <p role="alert">{t("ollama.model_missing")}</p>}
    {error && <p role="alert">{error}</p>}
    {provider === "groq" && <p className="field-help">{t("groq.capabilityHint")}</p>}
    {value && capabilities?.tools !== true && <p role="status">{t("playground.activity.unsupported")} {t("playground.activity.limited")}</p>}
    {value && <p>{t("ollama.tools")}: {t(capabilities?.tools ? "ollama.compatible" : "ollama.unknown")} · {t("ollama.vision")}: {t(capabilities?.vision ? "ollama.compatible" : "ollama.unknown")}</p>}
    <p className="field-help">{t("ollama.visionHint")}</p>
  </div>;
}
