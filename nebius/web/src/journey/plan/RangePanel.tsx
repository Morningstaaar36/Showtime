/** "How sure are these numbers?" on Your plan: the run the verdict rests on, again with 20%
 * fewer/more people and walking 15% slower/faster, with the range over the runs that finished
 * and which assumptions break the plan. Failed runs stay listed and are left out. */
import { Gauge } from "lucide-react";
import { toast } from "sonner";
import { useSensitivity, useStartSensitivity } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress, Spinner } from "@/components/ui/misc";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { itemEvidence, itemNumbers, itemOutcome, rangeVerdict, spreadText } from "./range";
import { metricText } from "./rewind";

const OUTCOME_TONE = { breaks: "danger", holds: "egress", failed: "caution", waiting: "outline" } as const;
const VERDICT_TONE = { egress: "text-egress", danger: "text-danger", neutral: "text-ink" } as const;

export function RangePanel({ sessionId }: { sessionId: string | null }) {
  const rec = useSensitivity(sessionId).data ?? null;
  const start = useStartSensitivity(sessionId);
  const running = rec?.status === "running" || start.isPending;
  const run = () => start.mutate(undefined, {
    onError: (e) => toast.error(e.message, { description: (e as { hint?: string | null }).hint ?? undefined }),
  });
  const checked = rec && rec.status !== "none";
  const verdict = checked ? rangeVerdict(rec) : null;
  const n = rec?.range?.evac_time_p95_s?.n ?? rec?.range?.peak_density_ppm2?.n ?? 0;

  return (
    <section aria-labelledby="range-h" className="min-w-0 space-y-3 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <h2 id="range-h" className="flex items-center gap-2 font-semibold"><Gauge className="size-4 text-signal" />{t("range.title")}</h2>
          <p className="text-sm text-muted">{t("range.body")}</p>
        </div>
        <Button variant={checked ? "secondary" : "primary"} className="min-h-11" onClick={run} disabled={running || (rec ? !rec.available : true)}>
          {running ? <Spinner /> : <Gauge />}{checked && !running ? t("range.again") : t("range.start")}
        </Button>
      </div>
      {rec && !rec.available && rec.reason && <p className="text-sm text-muted">{t("range.unavailable", { reason: rec.reason })}</p>}
      {rec && rec.status === "none" && rec.available && <p className="text-sm text-muted">{t("range.none")}</p>}

      {checked && verdict && (
        <div role="status" aria-live="polite" className="space-y-1.5">
          <p className={cn("font-semibold", VERDICT_TONE[verdict.tone])}>{verdict.text}</p>
          {rec.status === "running" && <Progress value={rec.total ? Math.round((100 * rec.done) / rec.total) : 0} tone="signal" />}
        </div>
      )}

      {checked && rec.range && (
        <dl className="grid gap-2 sm:grid-cols-3">
          {([["evac", spreadText(rec.range.evac_time_p95_s, "time")], ["peak", spreadText(rec.range.peak_density_ppm2, "density")],
            ["inside", spreadText(rec.range.agents_not_evacuated, "people")]] as const).map(([k, v]) => (
            <div key={k} className="rounded-[8px] border border-border p-2.5">
              <dt className="text-xs text-muted">{t(`range.${k}`)}</dt>
              <dd className="text-lg font-semibold tabular">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      {checked && rec.range && <p className="text-xs text-muted">{t("range.over", { n })}</p>}

      {checked && rec.items.length > 0 && (
        <div className="overflow-auto rounded-[8px] border border-border">
          <table className="w-full min-w-[36rem] border-collapse text-sm">
            <caption className="sr-only">{t("range.title")}</caption>
            <thead className="bg-surface-2">
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-2 py-2 font-medium">{t("range.col_assumption")}</th>
                <th scope="col" className="px-2 py-2 text-right font-medium">{t("range.col_evac")}</th>
                <th scope="col" className="px-2 py-2 text-right font-medium">{t("range.col_peak")}</th>
                <th scope="col" className="px-2 py-2 text-right font-medium">{t("range.col_inside")}</th>
                <th scope="col" className="px-2 py-2 font-medium">{t("range.col_result")}</th>
                <th scope="col" className="px-2 py-2 font-medium">{t("range.col_evidence")}</th>
              </tr>
            </thead>
            <tbody>
              {rec.items.map((item) => {
                const o = itemOutcome(item);
                const nums = itemNumbers(item);
                const shown = o === "breaks" || o === "holds";
                return (
                  <tr key={item.variant} className={cn("border-t border-border align-top", o === "failed" && "bg-caution-soft/50")}>
                    <th scope="row" className="px-2 py-1.5 text-left font-normal">{item.label}</th>
                    <td className="px-2 py-1.5 text-right tabular">{shown ? metricText("evac_time_95_s", nums) : "–"}</td>
                    <td className="px-2 py-1.5 text-right tabular">{shown ? metricText("peak_density_ppm2", nums) : "–"}</td>
                    <td className="px-2 py-1.5 text-right tabular">{shown ? metricText("people_inside", nums) : "–"}</td>
                    <td className="px-2 py-1.5">
                      <Badge tone={OUTCOME_TONE[o]}>{t(`range.${o}`)}</Badge>
                      {o === "breaks" && <p className="mt-1 text-xs text-muted">{item.breaks.join("; ")}</p>}
                      {o === "failed" && item.error && <p className="mt-1 text-xs text-muted">{item.error}</p>}
                    </td>
                    <td className="px-2 py-1.5 text-xs text-muted">{itemEvidence(item)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {checked && rec.notes.length > 0 && <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted">{rec.notes.map((note) => <li key={note}>{note}</li>)}</ul>}
    </section>
  );
}
