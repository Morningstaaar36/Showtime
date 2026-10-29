/** Header and page frame for the screens outside the guided journey: Projects, Settings, Help,
 * the first-run checklist and "page not found". The journey header uses the same links
 * (`AppNav`). The provider and sandbox badges are on Settings and in Expert view's top bar. */
import { CircleHelp, FolderOpen, type LucideIcon, Settings, Sparkles } from "lucide-react";
import type * as React from "react";
import { Link, NavLink } from "react-router";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

const NAV: { to: string; key: string; icon: LucideIcon; end?: boolean }[] = [
  { to: "/", key: "common.plan_event", icon: Sparkles, end: true },
  { to: "/projects", key: "common.your_plans", icon: FolderOpen },
  { to: "/settings", key: "nav.settings", icon: Settings },
  { to: "/help", key: "nav.help", icon: CircleHelp },
];

/** The app's main links, in both headers; `from` leaves out the first ones (the journey header's
 * logo already goes home). Labels show from `md` up, icons always. */
export function AppNav({ from = 0, labelsFrom = "md" }: { from?: number; labelsFrom?: "md" | "xl" }) {
  return (
    <nav aria-label={t("common.main_nav")} className="flex items-center gap-0.5 sm:gap-1">
      {NAV.slice(from).map(({ to, key, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} title={t(key)}
                 className={({ isActive }) => cn(
                   "flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-[var(--radius-control)] px-2.5 text-sm font-medium transition-colors lg:px-3",
                   isActive ? "bg-signal-soft text-signal" : "text-muted hover:bg-surface-2 hover:text-ink")}>
          <Icon className="size-4 shrink-0" aria-hidden /><span className={labelsFrom === "xl" ? "sr-only xl:not-sr-only" : "sr-only md:not-sr-only"}>{t(key)}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export function AppHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-1 px-4 sm:gap-2">
        <Link to="/" aria-label={t("common.home_label")} className="mr-1 flex min-h-11 items-center rounded-[var(--radius-control)] sm:mr-4">
          <Logo compact className="sm:hidden" /><Logo className="hidden sm:inline-flex" />
        </Link>
        <AppNav />
        <div className="ml-auto flex items-center gap-1 sm:gap-2"><ThemeToggle /></div>
      </div>
    </header>
  );
}

/** Header, page content and the disclaimer footer. */
export function AppShell({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className="flex min-h-full flex-col">
      <AppHeader />
      <main id="main" className={cn("flex-1", className)}>{children}</main>
      <footer className="border-t border-border px-4 py-3 text-center text-xs text-muted">{t("app.disclaimer")}</footer>
    </div>
  );
}
