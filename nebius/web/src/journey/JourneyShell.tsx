/** Frame of the guided journey: Describe, AI at work, Your plan. The studio stays one link away
 * as Expert view (from desktop width, the only width it works at); Settings and Help are the app
 * header's own links. */
import { Check, ChevronLeft, PanelsTopLeft } from "lucide-react";
import type * as React from "react";
import { Link } from "react-router";
import { Logo } from "@/components/Logo";
import { AppNav } from "@/app/AppHeader";
import { ThemeToggle } from "@/components/ThemeToggle";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

type JourneyStep = "describe" | "work" | "plan";
const STEPS: JourneyStep[] = ["describe", "work", "plan"];

function StepIndicator({ step, projectId }: { step: JourneyStep; projectId?: string }) {
  const at = STEPS.indexOf(step);
  const href = (s: JourneyStep) => !projectId ? "/" : s === "describe" ? `/p/${projectId}/describe` : s === "work" ? `/p/${projectId}/work` : `/p/${projectId}`;
  return (
    <ol aria-label={t("journey.steps")} className="flex items-center gap-1 text-sm">
      {STEPS.map((s, i) => {
        const done = i < at;
        const current = i === at;
        const label = <><span className={cn("grid size-6 place-items-center rounded-full text-xs font-semibold tabular",
            // one signal colour: a done step is not "safe", so it is not green
            current ? "bg-signal text-signal-ink ring-4 ring-signal-soft" : done ? "bg-signal-soft text-signal" : "bg-surface-3 text-muted")}>
            {done ? <Check className="size-3" /> : i + 1}
          </span><span className={cn("hidden whitespace-nowrap sm:inline", current ? "font-semibold text-ink" : "text-muted")}>{t(`journey.${s}`)}</span></>;
        return (
          <li key={s} className="flex items-center gap-1">
            {i > 0 && <span aria-hidden className="h-px w-3 bg-border-strong max-[359px]:hidden sm:mx-1 sm:w-8" />}
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

export function JourneyShell({ step, projectId, title, back, children, wide, fill }: {
  step: JourneyStep; projectId?: string; title?: string; back?: { to: string; label: string };
  children: React.ReactNode; wide?: boolean;
  /** lock to the window height on desktop, so a long side panel scrolls instead of stretching the 3D view */
  fill?: boolean;
}) {
  return (
    <div className={cn("flex min-h-full flex-col", fill && "lg:h-dvh lg:overflow-hidden")}>
      <header className="sticky top-0 z-30 border-b border-border bg-surface/85 backdrop-blur-md">
        <div className={cn("mx-auto flex h-14 items-center gap-2 px-4 max-[359px]:gap-1 max-[359px]:px-3 sm:gap-3", wide ? "max-w-none" : "max-w-6xl")}>
          {back ? (
            <Link to={back.to} className="flex min-h-11 items-center gap-1 text-sm text-muted hover:text-ink" aria-label={back.label}>
              <ChevronLeft className="size-4" /><Logo compact />
            </Link>
          ) : <Link to="/" aria-label={t("ui.journeyshell.showtime_home")}><Logo wordmarkClassName="max-sm:hidden" /></Link>}
          {title && <span className="hidden min-w-0 max-w-[22rem] truncate font-semibold md:inline">{title}</span>}
          <div className="mx-auto"><StepIndicator step={step} projectId={projectId} /></div>
          {projectId && (
            <Link to={`/p/${projectId}/expert`} aria-label={t("journey.expert")} title={t("journey.expert")}
                  className="hidden min-h-11 items-center lg:flex gap-1.5 rounded-[var(--radius-control)] px-2 text-sm text-muted hover:bg-surface-2 hover:text-ink">
              <PanelsTopLeft className="size-4" /><span className="hidden whitespace-nowrap xl:inline">{t("journey.expert")}</span>
            </Link>
          )}
          <AppNav from={2} labelsFrom="xl" />
          <ThemeToggle />
        </div>
      </header>
      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
      <footer className="border-t border-border px-4 py-2 text-center text-xs text-muted">{t("app.disclaimer")}</footer>
    </div>
  );
}
