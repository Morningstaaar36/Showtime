/** Frame of the guided journey: Describe → AI at work → Your plan. The studio stays one link
 * away as Expert view. */
import { Check, ChevronLeft, CircleHelp, PanelsTopLeft } from "lucide-react";
import type * as React from "react";
import { Link } from "react-router";
import { Logo } from "@/components/Logo";
import { ProviderBadge } from "@/components/ProviderBadge";
import { ThemeToggle } from "@/components/ThemeToggle";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

export type JourneyStep = "describe" | "work" | "plan";
const STEPS: JourneyStep[] = ["describe", "work", "plan"];
/** Each step has its own colour so the journey reads at a glance. */
const STEP_TONE: Record<JourneyStep, string> = { describe: "bg-sky text-white", work: "bg-signal text-signal-ink", plan: "bg-egress text-white" };

export function StepIndicator({ step, projectId }: { step: JourneyStep; projectId?: string }) {
  const at = STEPS.indexOf(step);
  const href = (s: JourneyStep) => !projectId ? "/" : s === "describe" ? `/p/${projectId}/describe` : s === "work" ? `/p/${projectId}/work` : `/p/${projectId}`;
  return (
    <ol aria-label={t("journey.steps")} className="flex items-center gap-1 text-sm">
      {STEPS.map((s, i) => {
        const done = i < at;
        const current = i === at;
        const label = <><span className={cn("grid size-6 place-items-center rounded-full text-xs font-semibold tabular",
            current ? cn(STEP_TONE[s], "ring-4 ring-signal-soft") : done ? "bg-egress text-white" : "bg-surface-3 text-muted")}>
            {done ? <Check className="size-3" /> : i + 1}
          </span><span className={cn("hidden sm:inline", current ? "font-semibold text-ink" : "text-muted")}>{t(`journey.${s}`)}</span></>;
        return (
          <li key={s} className="flex items-center gap-1">
            {i > 0 && <span aria-hidden className="h-px w-3 bg-border-strong sm:mx-1 sm:w-8" />}
            {projectId && !current ? (
              <Link to={href(s)} className="flex min-h-11 items-center gap-1.5 rounded-[var(--radius-control)] px-1.5 hover:bg-surface-2">{label}</Link>
            ) : (
              <span aria-current={current ? "step" : undefined} className="flex min-h-11 items-center gap-1.5 px-1.5">{label}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function JourneyShell({ step, projectId, title, back, children, wide }: {
  step: JourneyStep; projectId?: string; title?: string; back?: { to: string; label: string };
  children: React.ReactNode; wide?: boolean;
}) {
  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-30 border-b border-border bg-surface/85 backdrop-blur-md">
        <div className={cn("mx-auto flex h-14 items-center gap-2 px-4 sm:gap-3", wide ? "max-w-none" : "max-w-6xl")}>
          {back ? (
            <Link to={back.to} className="flex min-h-11 items-center gap-1 text-sm text-muted hover:text-ink" aria-label={back.label}>
              <ChevronLeft className="size-4" /><Logo compact />
            </Link>
          ) : <Link to="/" aria-label="Showtime home"><Logo /></Link>}
          {title && <span className="hidden min-w-0 truncate font-semibold md:inline">{title}</span>}
          <div className="mx-auto"><StepIndicator step={step} projectId={projectId} /></div>
          {projectId && (
            <Link to={`/p/${projectId}/expert`} aria-label={t("journey.expert")} title={t("journey.expert")}
                  className="flex min-h-11 items-center gap-1.5 rounded-[var(--radius-control)] px-2 text-sm text-muted hover:bg-surface-2 hover:text-ink">
              <PanelsTopLeft className="size-4" /><span className="hidden lg:inline">{t("journey.expert")}</span>
            </Link>
          )}
          <Link to="/help" aria-label={t("journey.help")} title={t("journey.help")}
                className="flex min-h-11 items-center gap-1.5 rounded-[var(--radius-control)] px-2 text-sm text-muted hover:bg-surface-2 hover:text-ink">
            <CircleHelp className="size-4" /><span className="hidden lg:inline">{t("journey.help")}</span>
          </Link>
          <span className="hidden sm:block"><ProviderBadge /></span>
          <ThemeToggle />
        </div>
      </header>
      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
      <footer className="border-t border-border px-4 py-2 text-center text-xs text-muted">{t("app.disclaimer")}</footer>
    </div>
  );
}
