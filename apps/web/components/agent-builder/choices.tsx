"use client";
import Link from "next/link";
import { BookOpen, CalendarDays, Check, Globe, Handshake, Target, Wrench } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { appointmentTools, channels, toggle, type AgentCatalog, type BuilderContext } from "@/lib/agent-builder";
import { builder } from "@/lib/i18n/dicts/builder";

export function channelName(id: string) {
  return ({ whatsapp: "WhatsApp", whatsapp_cloud: "WhatsApp · Meta Cloud", instagram: "Instagram", messenger: "Messenger", widget: "Webchat", telegram: "Telegram", mercado_libre: "Mercado Libre", amazon: "Amazon" } as Record<string, string>)[id] || id;
}
export function ObjectiveChoices({ catalog, value, onChange }: { catalog: AgentCatalog; value: string[]; onChange: (items: string[]) => void }) {
  const { t, lang } = useLanguage();
  return <div className="builder-grid">{catalog.objectives.map(item => <button type="button" key={item.id} aria-pressed={value.includes(item.id)} className="builder-card" onClick={() => onChange(toggle(value, item.id))}><Target size={21} /><strong>{item.label[lang]}</strong><span>{builder[lang].objectiveCopy[item.id as keyof typeof builder.en.objectiveCopy] || ""}</span>{value.includes(item.id) && <Check className="builder-check" size={18} aria-label={t("builder.selected")} />}</button>)}</div>;
}
export function ChannelChoices({ catalog, value, onChange }: { catalog: AgentCatalog; value: string[]; onChange: (items: string[]) => void }) {
  const { t } = useLanguage();
  return <><p>{t("builder.channelsHelp")}</p><div className="builder-grid">{channels.map(id => <button type="button" key={id} disabled={!catalog.channels.includes(id)} aria-pressed={value.includes(id)} className="builder-card" onClick={() => onChange(toggle(value, id))}><Globe size={21} /><strong>{channelName(id)}</strong><span>{t(catalog.channels.includes(id) ? "builder.available" : "builder.soon")}</span>{id === "whatsapp" && <small>{t("builder.whatsappHelp")}</small>}</button>)}</div></>;
}
export function ToolChoices({ context, clientId, value, shared, onChange, onShared, managed = false }: { managed?: boolean; context: BuilderContext | null; clientId: string; value: string[]; shared: string[]; onChange: (items: string[]) => void; onShared: (items: string[]) => void }) {
  const { t } = useLanguage();
  const appointmentSelected = appointmentTools.every(id => value.includes(id));
  const toggleAppointments = () => onChange(appointmentSelected ? value.filter(id => !appointmentTools.includes(id)) : [...value.filter(id => !appointmentTools.includes(id)), ...appointmentTools]);
  return <>{managed && <p className="builder-note">{t("builder.objectiveAuto")}</p>}<div className="builder-grid">
    <button type="button" className="builder-card" disabled={managed} aria-pressed={value.includes("knowledge")} onClick={() => onChange(toggle(value, "knowledge"))}><BookOpen /><strong>{t("builder.toolNames.knowledge")}</strong><span>{t("builder.toolCopy.knowledge")}</span><small>{t("builder.available")}</small></button>
    <div className="builder-card"><button type="button" className="builder-card-inner" disabled={managed || !context?.appointments_ready} aria-pressed={appointmentSelected} onClick={toggleAppointments}><CalendarDays /><strong>{t("builder.toolNames.calendar")}</strong><span>{t("builder.toolCopy.calendar")}</span><small>{t(context?.appointments_ready ? "builder.available" : "builder.disconnected")}</small></button><Link href={`/appointments?client_id=${clientId}`} target="_blank" rel="noopener noreferrer">{t("builder.configure")}</Link></div>
    <div className="builder-card"><button type="button" className="builder-card-inner" disabled={managed || !context?.google_connected || !context.appointments_ready} aria-pressed={appointmentSelected && !!context?.google_connected} onClick={toggleAppointments}><CalendarDays /><strong>{t("builder.toolNames.google")}</strong><span>{t("builder.toolCopy.google")}</span><small>{t(context?.google_connected ? "builder.available" : "builder.disconnected")}</small></button><Link href={`/appointments?client_id=${clientId}`} target="_blank" rel="noopener noreferrer">{t(context?.google_connected ? "builder.configure" : "builder.connect")}</Link></div>
    <button type="button" className="builder-card" disabled={managed} aria-pressed={value.includes("escalate_to_human")} onClick={() => onChange(toggle(value, "escalate_to_human"))}><Handshake /><strong>{t("builder.toolNames.handoff")}</strong><span>{t("builder.toolCopy.handoff")}</span></button>
    {(["icloud", "crm", "sheets", "email", "mercado", "amazon"] as const).map(id => <button type="button" disabled className="builder-card" key={id}><Wrench /><strong>{t(`builder.toolNames.${id}`)}</strong><span>{t("builder.toolCopy.unavailable")}</span><small>{t("builder.soon")}</small></button>)}
    {(["webhooks", "api"] as const).map(id => <div className="builder-card" key={id}><Wrench /><strong>{t(`builder.toolNames.${id}`)}</strong><span>{t("builder.toolCopy.external")}</span><small>{t(context?.tools.length ? "builder.available" : "builder.disconnected")}</small><small>{t("builder.setupAfter")}</small></div>)}
  </div><p className="builder-note">{t("builder.calendarHelp")}</p>{!!context?.tools.length && <><p>{t("builder.sharedHelp")}</p><div className="builder-grid">{context.tools.map(tool => <button type="button" key={tool.id} className="builder-card" aria-pressed={shared.includes(tool.id)} onClick={() => onShared(toggle(shared, tool.id))}><Wrench /><strong>{tool.name}</strong><span>{tool.description}</span></button>)}</div></>}</>;
}
