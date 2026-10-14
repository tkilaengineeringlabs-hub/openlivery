"use client";

import { useState } from "react";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Provider, ProviderTest } from "@/types";

export function OllamaSettings({ state, onSaved }: { state?: Provider; onSaved: () => Promise<void> }) {
  const t = useT();
  const [name, setName] = useState(state?.name || "Ollama local");
  const [url, setUrl] = useState(state?.base_url || "");
  const [model, setModel] = useState(state?.default_model || "");
  const [token, setToken] = useState("");
  const [clearToken, setClearToken] = useState(false);
  const [models, setModels] = useState<string[] | null>(null);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [response, setResponse] = useState("");
  const dirty = url !== (state?.base_url || "") || token !== "" || clearToken;
  const payload = () => ({ name, base_url: url, default_model: model || null, ...(token || clearToken ? { api_key: token } : {}) });
  const invalidate = () => { setConnected(false); setModels(null); setNotice(""); setResponse(""); setError(""); };

  async function run(action: "test" | "save" | "probe" | "remove") {
    setBusy(true); setError(""); setNotice(""); setResponse("");
    try {
      if (action === "test") {
        setConnected(false);
        const result = await api<ProviderTest>("/providers/ollama/validate", { method: "POST", body: JSON.stringify(payload()) });
        setModels(result.models); setConnected(true);
      } else if (action === "save") {
        await api("/providers/ollama", { method: "PUT", body: JSON.stringify(payload()) });
        await onSaved();
        setNotice(t("ollama.saved"));
      } else if (action === "remove") {
        await api("/providers/ollama", { method: "DELETE" });
        await onSaved();
      } else {
        const result = await api<{ ok: boolean; response: string }>("/providers/ollama/probe", { method: "POST", body: JSON.stringify({ model }) });
        setNotice(t(result.ok ? "ollama.probe_ok" : "ollama.probe_unexpected"));
        setResponse(result.response);
      }
    } catch (err) { setError(messageFrom(err)); if (action === "test") setModels(null); }
    finally { setBusy(false); }
  }

  return <section className="form-section">
    <div className="section-copy"><h2>{t("ollama.title")}</h2><p>{t("ollama.description")}</p>
      <p role="status">{t(connected ? "ollama.connected" : state?.configured ? "ollama.configured" : "ollama.disconnected")}</p>
    </div>
    <div className="form-fields"><fieldset disabled={busy} style={{ border: 0, padding: 0, minWidth: 0 }} className="form-fields">
      <label>{t("ollama.name")}<input value={name} maxLength={180} onChange={(e) => setName(e.target.value)} /></label>
      <label>{t("ollama.server")}<input type="url" value={url} onChange={(e) => { setUrl(e.target.value); invalidate(); }} /></label>
      <p className="field-help">{t("ollama.hint")}</p>
      <details><summary>{t("ollama.auth")}</summary><label>{t("ollama.auth")}<input type="password" autoComplete="new-password" value={token} onChange={(e) => { setToken(e.target.value); invalidate(); }} /></label>
        <p className="field-help">{t("ollama.authHint")}</p><label><input type="checkbox" checked={clearToken} onChange={(e) => { setClearToken(e.target.checked); invalidate(); }} />{t("ollama.clearAuth")}</label></details>
      <div className="form-actions"><button type="button" className="button secondary" disabled={!url.trim()} onClick={() => run("test")}>{t("ollama.test")}</button>
        <button type="button" className="button ghost" disabled={!url.trim()} onClick={() => run("test")}>{t("ollama.refresh")}</button></div>
      <label>{t("ollama.optional")}<select value={model} onChange={(e) => { setModel(e.target.value); setNotice(""); setResponse(""); }}><option value="">—</option>
        {model && !models?.includes(model) && <option value={model}>{model}</option>}
        {(models || []).map((id) => <option key={id} value={id}>{id}</option>)}
      </select></label>
      {models?.length === 0 && <p>{t("ollama.empty")}</p>}
      <div className="form-actions"><button type="button" className="button primary" disabled={!url.trim() || !name.trim() || (!!model && !models?.includes(model))} onClick={() => run("save")}>{t("ollama.save")}</button>
        <button type="button" className="button secondary" disabled={!state?.configured || dirty || !model} onClick={() => run("probe")}>{t("ollama.probe")}</button>
        {state?.configured && <button type="button" className="button danger" onClick={() => run("remove")}>{t("ollama.remove")}</button>}</div>
    </fieldset>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}{response && <pre>{response}</pre>}
    </div>
  </section>;
}
