"use client";

import "./login.css";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ChartNoAxesCombined,
  Cable,
  Workflow,
  ChevronRight,
  ArrowRight,
  Bot,
  CalendarDays,
  Clock3,
  Facebook,
  Globe2,
  Instagram,
  LayoutDashboard,
  LoaderCircle,
  MessageCircle,
  MessageSquareText,
  ShieldCheck,
  UsersRound,
  type LucideIcon,
} from "lucide-react";
import Image from "next/image";
import { login } from "@/lib/i18n/dicts/login";

import { api, messageFrom } from "@/lib/api";
import { Alert } from "@/components/ui";
import { PasswordInput } from "@/components/password-input";

// This landing page uses Spanish without changing the application language.
type I18nKey = `login.${keyof typeof login.es}`;
const t = (key: I18nKey) => login.es[key.slice(6) as keyof typeof login.es];

type AuthStatus = { needs_setup: boolean; registration_open: boolean };
type AutomationStatus = I18nKey;

const navItems: I18nKey[] = ["login.home", "login.conversations", "login.clients", "login.aiAgents", "login.automations", "login.appointments", "login.integrations", "login.reports"];
const navIcons: LucideIcon[] = [LayoutDashboard, MessageSquareText, UsersRound, Bot, Workflow, CalendarDays, Cable, ChartNoAxesCombined];
const kpis: { label: I18nKey; value: string; delta: string; icon: LucideIcon }[] = [
  { label: "login.activeClients", value: "248", delta: "+12%", icon: UsersRound },
  { label: "login.agents", value: "12", delta: "+33%", icon: Bot },
  { label: "login.conversations", value: "1,842", delta: "+18%", icon: MessageSquareText },
  { label: "login.appointmentsToday", value: "36", delta: "+20%", icon: CalendarDays },
];
const automations: { title: I18nKey | "Google Calendar" | "WhatsApp"; description: I18nKey; status: AutomationStatus; icon: LucideIcon }[] = [
  { title: "login.veterinary", description: "login.appointmentReminders", status: "login.active", icon: UsersRound },
  { title: "login.receptionist", description: "login.receptionistDescription", status: "login.active", icon: Bot },
  { title: "login.reminder", description: "login.reminderDescription", status: "login.ready", icon: Clock3 },
  { title: "Google Calendar", description: "login.calendarDescription", status: "login.active", icon: CalendarDays },
  { title: "WhatsApp", description: "login.whatsappDescription", status: "login.active", icon: MessageCircle },
];
const channels: { label: string; icon: LucideIcon | null; className: string }[] = [
  { label: "WhatsApp", icon: MessageCircle, className: "whatsapp" },
  { label: "Instagram", icon: Instagram, className: "instagram" },
  { label: "Messenger", icon: Facebook, className: "messenger" },
  { label: "Webchat", icon: Globe2, className: "webchat" },
  { label: "Google Calendar", icon: CalendarDays, className: "calendar" },
  { label: "+", icon: null, className: "plus" },
];

function TkilaBoxLogo() {
  return (
    <Image src="/brand/tkila-box-logo.svg" alt="" width={36} height={36}
      className="block size-9 shrink-0 object-contain" aria-hidden="true" />
  );
}

function DashboardPreview() {
  return (
    <div className="order-2 mt-6 grid min-h-[500px] w-full max-w-[760px] grid-cols-1 overflow-hidden rounded-[20px] border border-[#DCE4EC] bg-white shadow-[0_12px_36px_rgba(15,41,66,0.04)] min-[68.75rem]:grid-cols-[180px_minmax(0,1fr)]" aria-hidden="true">
      <aside className="hidden border-r border-[#DCE4EC] bg-[#F7F9FC]/80 px-3 py-5 min-[68.75rem]:block">
        <div className="mb-7 flex items-center gap-2 whitespace-nowrap text-[15px] font-bold"><TkilaBoxLogo /><span>Tkila Box</span></div>
        <nav className="flex flex-col gap-1">
          {navItems.map((item, index) => {
            const Icon = navIcons[index];
            return (
              <span className={`flex items-center gap-2.5 rounded-[10px] px-3 py-[9px] text-[13px] ${item === "login.home" ? "bg-[#F2FFD8] text-[#0F2942] font-semibold" : "text-[#64748B]"}`} key={item}><Icon size={14} className="shrink-0" />{t(item)}</span>
            );
          })}
        </nav>
      </aside>
      <section className="@container min-w-0 p-4 sm:p-5 xl:p-6">
        <div className="min-w-0">
          <header className="flex items-start justify-between gap-3 [&_h2]:m-0 [&_h2]:text-sm [&_h2]:font-bold [&_p]:mt-1 [&_p]:mb-0 [&_p]:text-xs [&_p]:text-[#64748B] [&_button]:shrink-0 [&_button]:rounded-md [&_button]:border [&_button]:border-[#DCE4EC] [&_button]:bg-white [&_button]:px-2 [&_button]:py-1.5 [&_button]:text-[10px]">
            <div>
              <h2>{t("login.overview")}</h2>
              <p>{t("login.overviewDescription")}</p>
            </div>
            <button type="button" tabIndex={-1}>{t("login.lastWeek")}</button>
          </header>
          <div className="mt-5 grid grid-cols-2 gap-3 @min-[360px]:grid-cols-4">
            {kpis.map(({ label, value, delta, icon: Icon }) => (
              <article className="flex min-h-[110px] min-w-0 flex-col gap-1.5 rounded-xl border border-[#DCE4EC] bg-white p-3 [&>span]:text-[#0F2942] [&>small]:min-h-[25px] [&>small]:break-words [&>small]:text-[10px] [&>small]:leading-tight [&>small]:text-[#64748B] [&>strong]:text-[20px] xl:[&>strong]:text-[24px] [&>strong]:leading-tight [&>em]:text-[10px] [&>em]:font-medium [&>em]:text-[#16A34A] [&>em]:not-italic" key={label}>
                <span className="flex h-4 items-center"><Icon size={16} /></span>
                <small>{t(label)}</small>
                <strong>{value}</strong>
                <em>{delta}</em>
              </article>
            ))}
          </div>
          <div className="mt-6 flex items-start justify-between gap-3 [&_h3]:m-0 [&_h3]:text-[13px] [&_h3]:font-bold [&_p]:mt-1 [&_p]:mb-0 [&_p]:text-[11px] [&_p]:leading-relaxed [&_p]:text-[#64748B] [&>span]:flex [&>span]:shrink-0 [&>span]:items-center [&>span]:gap-1 [&>span]:text-[10px] [&>span]:text-[#0F2942]">
            <div>
              <h3>{t("login.yourAutomations")}</h3>
              <p>{t("login.automationsDescription")}</p>
            </div>
            <span>{t("login.viewAll")} <ArrowRight size={13} /></span>
          </div>
          <div className="mt-3">
            {automations.map(({ title, description, status, icon: Icon }) => (
              <div className="flex items-center justify-between gap-3 border-b border-[#DCE4EC]/60 px-1 py-3.5 last:border-0 [&>p]:m-0 [&>p]:min-w-0 [&>p]:flex-1 [&_strong]:block [&_strong]:text-[11px] [&_strong]:font-semibold [&_strong]:leading-snug [&_small]:mt-0.5 [&_small]:block [&_small]:text-[10px] [&_small]:leading-relaxed [&_small]:text-[#64748B]" key={title}>
                <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-[#F2FFD8] text-[#0F2942]"><Icon size={16} /></span>
                <p><strong>{title === "Google Calendar" || title === "WhatsApp" ? title : t(title)}</strong><small>{t(description)}</small></p>
                <span className="flex shrink-0 items-center gap-1 text-[10px] text-[#16A34A]"><span className="size-1.5 rounded-full bg-[#16A34A]" />{t(status)}<ChevronRight size={12} className="text-slate-400" /></span>
              </div>
            ))}
          </div>
        </div>
      </section>

    </div>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);

  useEffect(() => {
    api<AuthStatus>("/auth/status")
      .then((status) => {
        setAuthStatus(status);
        if (status.needs_setup) setMode("register");
      })
      .catch(() => setAuthStatus({ needs_setup: false, registration_open: true }));
  }, []);

  // First run (no agency yet) goes straight to setup; afterwards the register
  // tab only exists on multi-agency instances.
  const showTabs = Boolean(authStatus && !authStatus.needs_setup && authStatus.registration_open);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      await api(mode === "login" ? "/auth/login" : "/auth/register", { method: "POST", body: JSON.stringify(data) });
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(messageFrom(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main lang="es" className="tkila-login min-h-screen bg-[radial-gradient(ellipse_280px_240px_at_5%_10%,#0f294208,transparent),radial-gradient(ellipse_280px_240px_at_95%_80%,#8be8000a,transparent)] bg-[#F7F9FC] text-[#0F2942]">
      <header className="mx-auto flex h-[72px] w-full max-w-[1440px] items-center justify-between gap-6 px-5 md:px-12 xl:px-[60px]">
        <div className="flex shrink-0 items-center gap-2.5 text-[23px] font-bold"><TkilaBoxLogo /><strong>Tkila Box</strong></div>
        <small className="hidden max-w-[300px] text-right text-[13px] leading-snug font-normal text-[#64748B] sm:block">{t("login.tagline")}</small>
      </header>
      <div className="mx-auto grid w-full max-w-[1440px] min-h-[calc(100vh-72px)] grid-cols-1 items-center gap-12 px-5 py-10 md:grid-cols-2 md:gap-8 md:px-12 min-[68.75rem]:grid-cols-[minmax(0,58fr)_minmax(0,42fr)] min-[68.75rem]:gap-16 xl:gap-20 xl:px-[60px]">
        <section className="order-2 flex min-w-0 flex-col md:order-1">
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-[#0F2942]">{t("login.eyebrow")}</span>
          <h1 className="mt-4 mb-5 max-w-[590px] break-words text-[36px] leading-[1.06] font-bold tracking-[-0.035em] sm:text-[40px] md:text-[44px] min-[68.75rem]:text-[54px]">{t("login.headline")}</h1>
          <p className="mb-0 max-w-[570px] text-[16px] leading-relaxed text-[#64748B]">{t("login.description")}</p>
          <p className="mt-4 mb-0 flex items-center gap-3 text-[13px] leading-relaxed font-semibold text-[#0F2942]"><span aria-hidden="true" className="h-4 w-0.5 shrink-0 rounded-full bg-[#8BE800]" />{t("login.benefit")}</p>
          <DashboardPreview />
          <div className="order-1 mt-4 flex flex-wrap items-center gap-x-4 gap-y-3 text-xs text-[#64748B] md:order-3 md:mt-3 [&>div]:flex [&>div]:flex-wrap [&>div]:items-center [&>div]:gap-3.5">
            <strong className="font-medium">{t("login.connectChannels")}</strong>
            <div>
              {channels.map(({ label, icon: Icon, className }) => (
                  <span className={`flex size-9 items-center justify-center rounded-xl border border-[#DCE4EC] bg-white text-[#0F2942] ${className}`} key={label} title={label}>
                  {Icon ? <Icon size={17} /> : label}
                </span>
              ))}
            </div>
          </div>
        </section>
        <section className="order-1 min-w-0 md:order-2">
          <div className="mx-auto w-full max-w-[470px] md:mr-0 rounded-[20px] border border-[#DCE4EC] bg-white px-6 py-7 shadow-[0_20px_60px_rgba(15,41,66,0.07)] min-[68.75rem]:p-9 xl:p-10">
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#0F2942]"><ShieldCheck size={15} /> {t("login.secureAccess")}</span>
            <h2 className="mt-4 mb-3 text-[32px] leading-tight font-bold tracking-tight xl:text-[34px]">{mode === "register" ? t("login.registerTitle") : t("login.loginTitle")}</h2>
            <p className="m-0 text-sm leading-relaxed text-[#64748B]">{mode === "register" ? t("login.registerDescription") : t("login.loginDescription")}</p>
            {showTabs && <div className="auth-tabs">
              <button type="button" className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setError(""); }}>{t("login.signIn")}</button>
              <button type="button" className={mode === "register" ? "active" : ""} onClick={() => { setMode("register"); setError(""); }}>{t("login.createAccount")}</button>
            </div>}
            <form onSubmit={submit} className="mt-6 flex flex-col gap-4 [&_label]:flex [&_label]:flex-col [&_label]:gap-2 [&_label]:text-[13px] [&_label]:font-medium [&_label]:leading-normal [&_label]:text-[#0F2942] [&_input:not([type=checkbox])]:h-[50px] [&_input:not([type=checkbox])]:w-full [&_input:not([type=checkbox])]:min-w-0 [&_input:not([type=checkbox])]:rounded-xl [&_input:not([type=checkbox])]:border [&_input:not([type=checkbox])]:border-[#DCE4EC] [&_input:not([type=checkbox])]:bg-[#F8FAFC] [&_input:not([type=checkbox])]:px-3.5 [&_input]:text-sm [&_input]:text-[#0F2942]">
              {mode === "register" && <>
                <label>{t("login.agencyName")}<input name="agency_name" required minLength={2} placeholder={t("login.agencyPlaceholder")} /></label>
                <label>{t("login.yourName")}<input name="name" required minLength={2} placeholder={t("login.namePlaceholder")} /></label>
              </>}
              <label>{t("login.email")}<input name="email" required type="email" placeholder={t("login.emailPlaceholder")} /></label>
              <label>{t("login.password")}<PasswordInput toggleLabels={{ show: t("login.showPassword"), hide: t("login.hidePassword") }} className="!pr-11" name="password" required minLength={8} placeholder={t("login.passwordPlaceholder")} /></label>
              {mode === "login" && <div className="flex items-center justify-between gap-2 text-xs [&>button]:border-0 [&>button]:bg-transparent [&>button]:p-0 [&>button]:text-[#0F2942] [&>button]:text-[11px]">
                <label className="!flex-row !items-center !gap-2 !text-xs [&_input]:m-0 [&_input]:size-4 [&_input]:accent-[#0F2942]"><input type="checkbox" /> <span>{t("login.rememberMe")}</span></label>
                <button type="button" disabled>{t("login.forgotPassword")}</button>
              </div>}
              {error && <Alert>{error}</Alert>}
              <button className="flex h-[52px] w-full items-center justify-center gap-2 rounded-xl border-0 bg-[#0F2942] text-sm font-semibold text-white shadow-sm transition-[background-color,transform] duration-200 enabled:hover:bg-[#173A58] motion-safe:enabled:hover:-translate-y-px disabled:opacity-60" disabled={busy}>{busy && <LoaderCircle className="spin" size={17} />}{mode === "register" ? t("login.createAgency") : t("login.signIn")} <ArrowRight size={17} className="text-[#8BE800]" /></button>
            </form>
            <div className="my-6 flex items-center gap-3 text-xs text-[#64748B] before:h-px before:flex-1 before:bg-[#DCE4EC] after:h-px after:flex-1 after:bg-[#DCE4EC]"><span>{t("login.continueWith")}</span></div>
            <div className="grid grid-cols-2 gap-3 [&>button]:transition-colors [&>button]:duration-200 [&>button:hover]:bg-[#F7F9FC] [&>button]:flex [&>button]:h-[52px] [&>button]:items-center [&>button]:justify-center [&>button]:gap-2 [&>button]:rounded-xl [&>button]:border [&>button]:border-[#DCE4EC] [&>button]:bg-white [&>button]:text-sm [&>button]:text-[#0F2942] [&>button]:font-medium [&>button]:leading-none [&_img]:block [&_img]:size-5 [&_img]:shrink-0">
              <button type="button" disabled><Image src="/brand/google.svg" alt="" width={20} height={20} /> Google</button>
              <button type="button" disabled><Image src="/brand/apple.svg" alt="" width={20} height={20} /> Apple</button>
            </div>
            <p className="mt-6 mb-0 flex items-start gap-2 text-xs leading-relaxed text-[#64748B] [&_svg]:mt-0.5 [&_svg]:shrink-0"><ShieldCheck size={14} /> {t("login.security")}</p>
          </div>
        </section>
      </div>
    </main>
  );
}
