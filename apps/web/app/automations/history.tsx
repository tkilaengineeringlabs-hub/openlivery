"use client";

import { useCallback, useEffect, useState } from "react";
import { History } from "lucide-react";
import { api } from "@/lib/api";
import { useLanguage, type I18nKey } from "@/lib/i18n";
import { automations } from "@/lib/i18n/dicts/automations";
import { Alert, EmptyState } from "@/components/ui";
import { TableSkeleton } from "@/components/skeleton";
import type { Run } from "./types";

export function AutomationHistory({ id }: { id: string }) {
  const { t, lang } = useLanguage();
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [count, setCount] = useState(50);
  const [hasMore, setHasMore] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const rows: Run[] = [];
      for (let offset = 0; offset < count; offset += 50) rows.push(...await api<Run[]>(`/automations/${id}/runs?limit=50&offset=${offset}`));
      setRuns(rows); setHasMore(rows.length === count); setFailed(false);
    } catch { setFailed(true); }
    finally { setLoading(false); }
  }, [id, count]);
  useEffect(() => { void refresh(); const timer = setInterval(() => void refresh(), 10000); return () => clearInterval(timer); }, [refresh]);
  if (loading) return <TableSkeleton columns={6} />;
  return <section className="automation-history">
    <div className="automation-controls"><h2>{t("automations.history")}</h2><button className="button secondary" onClick={() => void refresh()}>{t("automations.refresh")}</button></div>
    {failed && <Alert>{t("automations.loadError")}</Alert>}
    {runs.length === 0 ? <EmptyState icon={<History />} title={t("automations.historyEmpty")} description={t("automations.historyHelp")} /> : <div className="table-shell"><table className="data-table"><thead><tr>{(["date", "event", "state", "actionsExecuted", "elapsed", "errorLabel"] as const).map(key => <th key={key}>{t(`automations.${key}`)}</th>)}</tr></thead><tbody>
      {runs.map(run => <tr key={run.id}><td>{new Date(run.started_at).toLocaleString(lang)}</td><td>{t(`automations.trigger.${run.event_type}`)}</td><td>{t(`automations.status.${run.status}`)}</td><td>{run.actions_executed} / {run.action_count}</td><td>{run.duration_seconds === null ? t("automations.status.running") : t("automations.seconds", { count: Math.round(run.duration_seconds) })}</td><td>{run.error ? t((Object.hasOwn(automations.en.errors, run.error) ? `automations.errors.${run.error}` : "automations.errors.execution_failed") as I18nKey) : "—"}</td></tr>)}
    </tbody></table></div>}
    {hasMore && <button className="button secondary" onClick={() => setCount(current => current + 50)}>{t("automations.more")}</button>}
  </section>;
}
