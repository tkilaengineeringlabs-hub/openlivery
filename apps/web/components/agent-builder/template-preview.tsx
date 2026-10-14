"use client";
import Link from "next/link";
import { useLanguage } from "@/lib/i18n";
import type { AgentCatalog, TemplatePreview as Preview } from "@/lib/agent-builder";
import { channelName } from "./choices";

export function TemplatePreview({ preview, catalog, clientId }: { preview: Preview; catalog: AgentCatalog; clientId: string }) {
  const { t, lang } = useLanguage();
  const item = preview.template;
  return <aside className="builder-note"><h3>{item.name[lang]}</h3><p>{item.description[lang]}</p><dl className="builder-summary">
    <dt>{t("builder.steps.objectives")}</dt><dd>{item.objectives.map(id => catalog.objectives.find(o => o.id === id)?.label[lang]).filter(Boolean).join(" · ")}</dd>
    <dt>{t("builder.steps.tools")}</dt><dd>{item.recommended_tools.map(id => <div key={id}>{catalog.tools.find(o => o.id === id)?.label[lang]}{preview.unavailable_tools.includes(id) && <> · {t("builder.disconnected")}</>}</div>)}</dd>

    <dt>{t("builder.steps.channels")}</dt><dd>{item.recommended_channels.map(channelName).join(" · ")}</dd>
    <dt>{t("builder.tone")}</dt><dd>{t(`builder.tones.${item.default_tone}`)}</dd>
    <dt>{t("builder.handoffRules")}</dt><dd>{item.handoff_rules.map(id => id === "human_request" ? t("builder.handoffRequest") : t("builder.handoffUnresolved")).join(" · ")}</dd>
  </dl>{preview.unavailable_tools.length > 0 && <p>{t("builder.missingTools")} {preview.unavailable_tools.some(id => id.includes("appointment")) ? <Link href={`/appointments?client_id=${clientId}`}>{t("builder.configure")}</Link> : t("builder.setupAfter")}</p>}
  {item.recommended_tools.some(id => id.includes("appointment")) && <p>Google Calendar · {t(preview.google_connected ? "builder.available" : "builder.disconnected")} <Link href={`/appointments?client_id=${clientId}`}>{t("builder.connect")}</Link></p>}
  {!!preview.missing_business_fields.length && <><strong>{t("builder.completeBusiness")}</strong><ul>{preview.missing_business_fields.map(field => <li key={field}>{t(`builder.businessFields.${field as keyof typeof import("@/lib/i18n/dicts/builder").builder.en.businessFields}`)}</li>)}</ul><p>{t("builder.fieldsHelp")}</p></>}
  {!!preview.warnings.length && <p role="status">{t("builder.retiredReferences")}</p>}
  <p>{t("builder.objectiveAuto")}</p></aside>;
}
