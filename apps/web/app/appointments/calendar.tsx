"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";
import { useToast } from "@/components/toast";
export type CalendarConnection = { configured: boolean; connected: boolean; account_email: string | null; calendar_id: string | null; calendar_name: string | null; sync_counts: Record<string, number> };
type CalendarChoice = { id: string; name: string; primary: boolean };
export function ConnectedCalendar({ clientId, connection, refresh }: { clientId: string; connection: CalendarConnection | null; refresh: () => void }) {
  const { t } = useLanguage(); const toast = useToast();
  const [choices, setChoices] = useState<CalendarChoice[]>([]), [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const base = `/appointment-calendars/${clientId}/google`;
  useEffect(() => {
    if (!connection?.connected) return;
    let live = true;
    api<CalendarChoice[]>(`${base}/calendars`).then(rows => { if (live) setChoices(rows); }).catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [base, connection?.connected]);
  async function run(work: () => Promise<void>) {
    setBusy(true);
    try { await work(); refresh(); } catch (error) {
      toast.error(t(error instanceof ApiError && error.message === "calendar_has_linked_appointments" ? "appointments.calendarLocked" : "appointments.calendarError"));
    } finally { setBusy(false); }
  }
  return <section className="form-section"><h2>{t("appointments.calendarTitle")}</h2><h3>Google Calendar</h3>
    <p>{t(connection?.connected ? "appointments.connected" : "appointments.notConnected")}</p>
    {!connection?.configured && <p>{t("appointments.calendarSetup")}</p>}
    {connection?.account_email && <p>{connection.account_email}</p>}
    {connection?.connected ? <>
      <label>{t("appointments.defaultCalendar")}<select disabled={busy || failed} value={connection.calendar_id || ""} onChange={e => { const id = e.target.value; if (id) void run(async () => { await api(`${base}/calendar`, { method: "PUT", body: JSON.stringify({ calendar_id: id }) }); }); }}>
        <option value="">{t("appointments.selectCalendar")}</option>{choices.map(c => <option key={c.id} value={c.id}>{c.name}{c.primary ? ` · ${t("appointments.primaryCalendar")}` : ""}</option>)}
      </select></label>
      {failed && <p role="alert">{t("appointments.calendarError")}</p>}
      <p>{t("appointments.syncHelp")}</p>
      <div className="appointment-toolbar">{(["pending", "synced", "error"] as const).map(state => <span key={state}>{t(`appointments.sync.${state}`)}: {connection.sync_counts[state] || 0}</span>)}</div>
      <button className="button secondary" disabled={busy} onClick={() => void run(async () => { await api(`${base}/retry`, { method: "POST" }); })}>{t("appointments.retrySync")}</button>
      <button className="button secondary" disabled={busy} onClick={() => { if (window.confirm(t("appointments.disconnectConfirm"))) void run(async () => { await api(base, { method: "DELETE" }); }); }}>{t("appointments.disconnect")}</button>
    </> : <button className="button primary" disabled={busy || !connection?.configured} onClick={() => void run(async () => { const result = await api<{ url: string }>(`${base}/connect`, { method: "POST" }); window.location.assign(result.url); })}>{t("appointments.connectGoogle")}</button>}
    <h3>Apple / iCloud Calendar</h3><p>{t("appointments.comingSoon")}</p>
  </section>;
}
