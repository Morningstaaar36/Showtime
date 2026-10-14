/** "Rewind the worst moment" on Your plan: go back to the second the worst attack was most
 * dangerous and compare every response, each resumed from that same second in its own
 * sandbox, with doing nothing. Numbers come from each branch's run; lower is better. */
import { History, Trophy } from "lucide-react";
import { toast } from "sonner";
import { useRewind, useStartRewind } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress, Spinner } from "@/components/ui/misc";
import { t } from "@/i18n";
import { fmtDuration } from "@/lib/format";
import { cn } from "@/lib/utils";
import { bestLine, METRICS, type MetricKey, rewindProgress, rewindRows } from "./rewind";

const COL: Record<MetricKey, string> = { evac_time_95_s: "evac", people_inside: "inside", peak_density_ppm2: "peak", time_above_danger_s: "danger" };

const TONE = { better: "text-[color-mix(in_srgb,var(--egress)_68%,black)] dark:text-egress", worse: "text-[color-mix(in_srgb,var(--danger)_80%,black)] dark:text-danger", same: "text-muted" };

/** `worstTitle` names the attack that broke the plan worst (none when nothing broke: the
 * rewind then uses the attack that came out worst); `canRewind` is false without attacks. */
export function RewindPanel({ sessionId, worstTitle, canRewind }: { sessionId: string; worstTitle: string | null; canRewind: boolean }) {
  const rewind = useRewind(sessionId);
  const start = useStartRewind(sessionId);
  const rec = rewind.data ?? null;
  const running = rec?.status === "running" || start.isPending;
  const run = () => start.mutate(undefined, { onError: (e) => toast.error(e.message) });
  const rows = rec ? rewindRows(rec) : [];
  const shown = rec && (rec.status === "done" || rec.status === "running") && rows.length > 0;

  return (
    <section aria-labelledby="rewind-h" className="space-y-3 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <h2 id="rewind-h" className="flex items-center gap-2 font-semibold"><History className="size-4 text-signal" />{t("rewind.title")}</h2>
          <p className="text-sm text-muted">{t("rewind.body")}</p>
          {(rec?.attack?.title ?? worstTitle) && <p className="text-sm">{t("rewind.under", { attack: rec?.attack?.title ?? worstTitle ?? "" })}</p>}
        </div>
        <Button variant={rec ? "secondary" : "primary"} className="min-h-11" onClick={run} disabled={running || !canRewind}>
          {running ? <Spinner /> : <History />}{start.isPending ? t("rewind.starting") : rec?.status === "done" ? t("rewind.again") : t("rewind.start")}
        </Button>
      </div>

      {rec?.status === "running" && (
        <div role="status" className="space-y-1.5 text-sm">
          <p>{rewindProgress(rec)}</p>
          <Progress value={rec.total ? (100 * rec.done) / rec.total : 5} />
        </div>
      )}
      {rec?.status === "unsupported" && (
        <div role="status" className="rounded-[8px] border border-caution/40 bg-caution-soft p-3 text-sm">
          <p className="font-medium">{t("rewind.unsupported")}</p>
          <p>{rec.message}</p>
        </div>
      )}
      {(rec?.status === "failed" || rec?.status === "interrupted" || rec?.status === "cancelled") && (
        <div role="status" className="rounded-[8px] border border-danger/40 bg-danger-soft p-3 text-sm">
          <p className="font-medium">{t("rewind.failed")}</p>
          <p>{rec.status === "interrupted" ? t("rewind.interrupted") : rec.message}</p>
        </div>
      )}

      {rec?.moment && rec.status !== "unsupported" && (
        <p className="text-sm">{t("rewind.moment", { time: fmtDuration(rec.moment.at_s), why: rec.moment.why })}</p>
      )}

      {shown && (
        <div className="-mx-1 overflow-x-auto px-1">
          <table className="w-full min-w-[40rem] border-collapse text-sm">
            <caption className="sr-only">{t("rewind.title")}</caption>
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted">
                <th scope="col" className="py-2 pr-2 font-medium">{t("rewind.col_response")}</th>
                {METRICS.map((k) => (
                  <th key={k} scope="col" className="px-2 py-2 text-right font-medium">{t(`rewind.col_${COL[k]}`)}</th>
                ))}
                <th scope="col" className="py-2 pl-2 font-medium">{t("rewind.col_evidence")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} data-best={r.best || undefined} className={cn("border-b border-border align-top last:border-b-0", r.best && "bg-egress-soft", r.nothing && "bg-surface-2")}>
                  <th scope="row" className="py-2 pr-2 text-left font-medium">
                    <span className="block">{r.label}</span>
                    <span className="mt-0.5 flex flex-wrap gap-1">
                      {r.best && <Badge tone="egress"><Trophy />{t("rewind.best")}</Badge>}
                      {!r.nothing && <Badge tone="outline">{t(`rewind.kind_${r.kind}`)}</Badge>}
                    </span>
                    {r.problem && <span className="mt-1 block text-xs font-normal text-muted">{r.problem}</span>}
                  </th>
                  {r.cells.map((c) => (
                    <td key={c.key} className="px-2 py-2 text-right tabular">
                      <span className="block">{c.value}</span>
                      {c.delta && <span className={cn("block text-xs", TONE[c.tone])}>{c.delta}</span>}
                    </td>
                  ))}
                  <td className="py-2 pl-2 text-xs text-muted">{r.evidence}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-muted">{t("rewind.lower_better")}</p>
        </div>
      )}

      {rec?.status === "done" && <p className="font-medium">{bestLine(rec)}</p>}
      {rec && rec.notes.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted">{rec.notes.map((n) => <li key={n}>{n}</li>)}</ul>
      )}
      {rec?.checkpoint_run_id && rec.status === "done" && (
        <p className="text-xs text-muted">{t("rewind.checkpoint", { run: rec.checkpoint_run_id })}</p>
      )}
    </section>
  );
}
