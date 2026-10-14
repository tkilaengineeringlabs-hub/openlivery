export type AppointmentStatus = "scheduled" | "confirmed" | "completed" | "cancelled" | "no_show";
export const statuses: AppointmentStatus[] = ["scheduled", "confirmed", "completed", "cancelled", "no_show"];
export type Service = { id: string; client_id: string; name: string; description: string; price: string | null; color: string | null; duration_minutes: number; buffer_before_minutes: number; buffer_after_minutes: number; active: boolean };
export type Appointment = { id: string; client_id: string; agent_id: string | null; conversation_id: string | null; service_id: string | null; service_name: string; customer_name: string; customer_phone: string | null; customer_email: string | null; starts_at: string; ends_at: string; timezone: string; status: AppointmentStatus; source: "manual" | "agent" | "whatsapp" | "web" | "automation" | "instagram"; notes: string; created_at: string; external_provider: string | null; calendar_sync_status: "pending" | "synced" | "error" | "not_connected"; calendar_sync_error: string | null };
export type Rule = { weekday: number; start_time: string; end_time: string; active: boolean };
export type Availability = { timezone: string; slot_minutes: number; min_notice_minutes?: number; booking_days?: number; reminders?: number[]; rules: Rule[] };
export type Block = { id: string; starts_at: string; ends_at: string; reason: string };
export type Slot = { starts_at: string; ends_at: string; available: boolean };
export function dateInZone(value: string | Date, zone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(value));
  const get = (name: string) => parts.find(p => p.type === name)?.value;
  return `${get("year")}-${get("month")}-${get("day")}`;
}
export function addDays(value: string, count: number) { const d = new Date(`${value}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + count); return d.toISOString().slice(0, 10); }
export function weekStart(value: string) { const d = new Date(`${value}T12:00:00Z`).getUTCDay(); return addDays(value, -(d + 6) % 7); }
export function minuteOfDay(value: string, zone: string) {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: zone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(value));
  return Number(parts.find(p => p.type === "hour")?.value) * 60 + Number(parts.find(p => p.type === "minute")?.value);
}
export function clock(value: string, zone: string, lang: string) { return new Intl.DateTimeFormat(lang, { timeZone: zone, hour: "2-digit", minute: "2-digit" }).format(new Date(value)); }
// Block inputs are business wall times, not browser-local dates. Reject DST gaps
// and ambiguous folds; booking forms use the backend's explicit-offset slots.
export function wallTimeToInstant(value: string, zone: string) {
  const wall = new Date(`${value}:00Z`).getTime();
  if (!Number.isFinite(wall)) throw new Error("invalid_time");
  const candidates = new Set<string>();
  for (const hours of [-24, 0, 24]) {
    const sample = new Date(wall + hours * 3600000);
    const day = dateInZone(sample, zone), minutes = minuteOfDay(sample.toISOString(), zone);
    const offset = new Date(`${day}T00:00:00Z`).getTime() + minutes * 60000 - sample.getTime();
    const candidate = new Date(wall - offset).toISOString();
    const expectedDay = value.slice(0, 10), expectedMinutes = Number(value.slice(11, 13)) * 60 + Number(value.slice(14, 16));
    if (dateInZone(candidate, zone) === expectedDay && minuteOfDay(candidate, zone) === expectedMinutes) candidates.add(candidate);
  }
  if (candidates.size !== 1) throw new Error("invalid_time");
  return [...candidates][0];
}
