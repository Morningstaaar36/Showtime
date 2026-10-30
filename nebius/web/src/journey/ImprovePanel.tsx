/** "Let the AI fix it" on Your plan: the AI accepts the fixes the simulator proved, tests the
 * plan again and repeats until no attack breaks it. Each test is listed with what broke and the
 * fixes it saved, and each one opens as a normal test (POST/GET /sessions/{id}/improve). */
import { Bot, CheckCircle2, CircleStop, ExternalLink, TriangleAlert } from "lucide-react";
import { Link } from "react-router";
import { toast } from "sonner";
import { useImprove, useStartImprove, useStopImprove } from "@/api/queries";
import type { ImproveLoop } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/misc";
import { t } from "@/i18n";
import { fmtDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Shown once a test has finished: the button while attacks still break the plan, or the loop. */
export function ImprovePanel({ projectId, sessionId, breaks }: {
  projectId: string; sessionId: string; breaks: number;
}) {
  const loop = useImprove(sessionId);
  const start = useStartImprove(sessionId);
  const stop = useStopImprove(sessionId);
  if (loop.isLoading) return null;
  const data = loop.data ?? null;
  if (!data && breaks === 0) return null;
  return (
    <section aria-labelledby="improve-h" data-testid="improve-panel"
             className="space-y-3 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h2 id="improve-h" className="flex items-center gap-2 font-semibold"><Bot className="size-4 text-signal" aria-hidden />{t("improve.title")}</h2>
          <p className="mt-0.5 max-w-prose text-sm text-muted">{data ? t("improve.lead_n", { n: data.max_rounds }) : t("improve.lead")}</p>
        </div>
        {!data || data.status !== "running" ? (
          !data && (
            <Button variant="secondary" disabled={start.isPending}
                    onClick={() => start.mutate(undefined, { onError: (e) => toast.error(t("improve.failed_start"), { description: e.message }) })}>
              {start.isPending ? <Spinner /> : <Bot />}{t("improve.start")}
            </Button>
          )
        ) : (
          <Button variant="ghost" disabled={stop.isPending || data.detail.startsWith("Stopping")} onClick={() => stop.mutate()}>
            <CircleStop />{t("improve.stop")}
          </Button>
        )}
      </div>
      {data && <Iterations loop={data} projectId={projectId} />}
    </section>
  );
}

function Iterations({ loop, projectId }: { loop: ImproveLoop; projectId: string }) {
  const running = loop.status === "running";
  const done = loop.status === "holds";
  return (
    <div className="space-y-2">
      <p role="status" className={cn("flex items-start gap-2 text-sm font-medium",
                                     done ? "text-egress" : running ? "text-ink" : "text-caution")}>
        {running ? <Spinner className="mt-0.5 size-4" /> : done ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <TriangleAlert className="mt-0.5 size-4 shrink-0" />}
        <span>{loop.detail}</span>
      </p>
      <ol className="space-y-1.5">
        {loop.iterations.map((it, i) => {
          const finished = it.breaks != null;
          const before = it.before.evac_time_p95_s;
          const after = it.after.evac_time_p95_s;
          return (
            <li key={it.session_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[8px] border border-border px-3 py-2 text-sm">
              <span className="font-medium">{t("improve.test", { n: i + 1, v: it.version })}</span>
              <span className={cn("tabular", !finished ? "text-muted" : it.breaks ? "text-danger" : "text-egress")}>
                {!finished ? t("improve.testing") : it.breaks ? t("improve.breaks", { b: it.breaks, a: it.attacks ?? "?" }) : t("improve.holds")}
              </span>
              {it.applied_version != null && (
                <span className="text-muted">
                  {t("improve.applied", { k: it.kept_fixes.length, v: it.applied_version })}
                  {it.fix_titles.length > 0 && <>: {it.fix_titles.join("; ")}</>}
                  {before != null && after != null && <span className="tabular"> · {t("improve.worst", { a: fmtDuration(before), b: fmtDuration(after) })}</span>}
                </span>
              )}
              <Link to={finished ? `/p/${projectId}?session=${it.session_id}` : `/p/${projectId}/work?session=${it.session_id}`}
                    className="ml-auto inline-flex min-h-9 items-center gap-1 text-xs font-semibold text-signal hover:underline">
                <ExternalLink className="size-3.5" aria-hidden />{finished ? t("improve.open") : t("improve.watch")}
              </Link>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
