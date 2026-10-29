/** The live sandbox feed on "AI at work": every run's sealed container, its state and time, and
 * for an AI-written scenario script, whether it ran, was refused, crashed or was stopped, and why. */
import { Ban, CircleCheck, CircleX, Clock3, Loader2, Recycle, ShieldCheck, Skull } from "lucide-react";
import type { SandboxRun } from "@/api/useSessionStream";
import { sandboxCounts } from "@/api/useSessionStream";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

// `tone` colours the icon; `text` the state word, in the darker shades that keep small text
// above the WCAG AA contrast ratio
const STATE: Record<SandboxRun["state"], { icon: React.ReactNode; tone: string; text: string }> = {
  queued: { icon: <Clock3 />, tone: "text-muted", text: "text-muted" },
  running: { icon: <Loader2 className="animate-spin motion-reduce:animate-none" />, tone: "text-signal", text: "text-signal" },
  finished: { icon: <CircleCheck />, tone: "text-egress", text: "text-egress-strong" },
  reused: { icon: <Recycle />, tone: "text-muted", text: "text-muted" },
  refused: { icon: <Ban />, tone: "text-danger", text: "text-danger-strong" },
  killed: { icon: <Skull />, tone: "text-danger", text: "text-danger-strong" },
  failed: { icon: <CircleX />, tone: "text-caution", text: "text-caution-strong" },
  cancelled: { icon: <CircleX />, tone: "text-muted", text: "text-muted" },
};

/** The line under a run: why a script was refused or stopped, or why the run was killed. */
export function sandboxWhy(r: SandboxRun): { text: string; tone: "danger" | "caution" } | null {
  if (r.script?.state === "refused") return { text: t("work.sbx_why_refused", { why: r.script.reason ?? "" }), tone: "danger" };
  if (r.script?.state === "stopped") return { text: t("work.sbx_why_stopped", { why: r.script.reason ?? "" }), tone: "caution" };
  if (r.script?.state === "error") return { text: t("work.sbx_why_error", { why: r.script.reason ?? "" }), tone: "caution" };
  if ((r.state === "killed" || r.state === "failed") && r.reason) return { text: r.reason, tone: r.state === "killed" ? "danger" : "caution" };
  if (r.retried && r.state === "finished") return { text: t("work.sbx_why_retried", { why: r.retried }), tone: "caution" };
  return null;
}

export function SandboxFeed({ runs, className }: { runs: SandboxRun[]; className?: string }) {
  const c = sandboxCounts(runs);
  const limits = runs.find((r) => r.limits)?.limits;
  const newest = [...runs].reverse();
  return (
    <section aria-labelledby="sbx-h" className={cn("rounded-[var(--radius-panel)] border border-border bg-surface p-3 shadow-sm", className)} data-testid="sandbox-feed">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="sbx-h" className="flex items-center gap-1.5 text-sm font-semibold"><ShieldCheck className="size-4 text-egress" aria-hidden />{t("work.sbx_title")}</h2>
        <p className="text-xs text-muted tabular" aria-live="polite">
          {c.total ? t("work.sbx_counts", { done: c.done, total: c.total, running: c.running }) : t("work.sbx_none")}
        </p>
      </div>
      {limits && <p className="mt-1 text-2xs text-muted">{limits}</p>}
      {newest.length > 0 && (
        <ul className="scrollbar-thin mt-2 max-h-64 space-y-1.5 overflow-y-auto pr-1">
          {newest.map((r) => {
            const s = STATE[r.state] ?? STATE.finished;
            const why = sandboxWhy(r);
            return (
              <li key={r.run_id} className="text-sm" data-testid="sandbox-row" data-state={r.state}>
                <div className="flex items-center gap-2">
                  <span className={cn("shrink-0 [&_svg]:size-4", s.tone)} aria-hidden>{s.icon}</span>
                  <span className="min-w-0 flex-1 truncate" title={`${r.label} · ${r.run_id}`}>{r.label}</span>
                  <span className={cn("shrink-0 text-2xs font-medium", s.text)}>{t(`work.sbx_state_${r.state}`)}</span>
                  <span className="w-10 shrink-0 text-right text-2xs text-muted tabular">{r.state === "queued" || r.state === "reused" || !Number.isFinite(r.elapsed_s) ? "" : t("units.n_s", { n: Math.round(r.elapsed_s) })}</span>
                </div>
                {why && <p className={cn("ml-6 mt-0.5 text-2xs", why.tone === "danger" ? "text-danger-strong" : "text-caution-strong")}>{why.text}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
