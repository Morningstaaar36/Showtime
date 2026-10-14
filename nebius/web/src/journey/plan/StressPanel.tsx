/** "Stress test at scale" on Your plan: every attack × (the plan + each kept change) × a few
 * random crowds, run at once in parallel sandboxes, with a live counter and a results table.
 * Failed runs stay listed with their reason. */
import { Layers } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useStartStress, useStress } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress, Spinner } from "@/components/ui/misc";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { metricText } from "./rewind";
import { failures, rowEvidence, rowOutcome, stressCounter, stressSummary } from "./stress";

const OUTCOME_TONE = { breaks: "danger", holds: "egress", failed: "caution", waiting: "outline" } as const;
const control = "min-h-11 rounded-[var(--radius-control)] border border-border bg-surface px-3 text-sm";

export function StressPanel({ projectId, hasTest }: { projectId: string; hasTest: boolean }) {
  const stress = useStress(projectId);
  const start = useStartStress(projectId);
  const [seeds, setSeeds] = useState(2);
  const [attacks, setAttacks] = useState<"session" | "rules">(hasTest ? "session" : "rules");
  const [withFixes, setWithFixes] = useState(true);
  const rec = stress.data ?? null;
  const running = rec?.status === "running" || start.isPending;
  const run = () => start.mutate({ attacks, seeds, include_fixes: withFixes }, {
    onError: (e) => toast.error(e.message, { description: (e as { hint?: string | null }).hint ?? undefined }),
  });
  const counter = rec ? stressCounter(rec) : null;
  const failed = rec ? failures(rec) : [];

  return (
    <section aria-labelledby="stress-h" className="space-y-3 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
      <div className="space-y-1">
        <h2 id="stress-h" className="flex items-center gap-2 font-semibold"><Layers className="size-4 text-signal" />{t("stress.title")}</h2>
        <p className="text-sm text-muted">{t("stress.body")}</p>
      </div>
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="text-muted">{t("stress.attacks")}</span>
          <select className={control} value={attacks} onChange={(e) => setAttacks(e.target.value as "session" | "rules")} disabled={running}>
            <option value="session">{t("stress.attacks_session")}</option>
            <option value="rules">{t("stress.attacks_rules")}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-muted">{t("stress.seeds")}</span>
          <select className={control} value={seeds} onChange={(e) => setSeeds(Number(e.target.value))} disabled={running}>
            {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="flex min-h-11 items-center gap-2">
          <input type="checkbox" className="size-5 accent-[var(--signal)]" checked={withFixes} onChange={(e) => setWithFixes(e.target.checked)} disabled={running} />
          {t("stress.include_fixes")}
        </label>
        <Button variant={rec ? "secondary" : "primary"} className="min-h-11" onClick={run} disabled={running}>
          {running ? <Spinner /> : <Layers />}{rec && !running ? t("stress.again") : t("stress.start")}
        </Button>
      </div>

      {rec && counter && (
        <div role="status" aria-live="polite" className="space-y-1.5">
          <p className="flex flex-wrap items-baseline gap-x-3 text-lg font-semibold tabular">
            {counter.text}{counter.failed && <span className="text-sm font-normal text-[color-mix(in_srgb,var(--caution)_62%,black)] dark:text-caution">{counter.failed}</span>}
          </p>
          <Progress value={counter.pct} tone={rec.failed ? "danger" : "signal"} />
          <p className="text-xs text-muted">{t("stress.parallel", { n: rec.parallel })}</p>
          {rec.status === "interrupted" && <p className="text-sm">{t("stress.interrupted")}</p>}
          {rec.message && rec.status !== "interrupted" && <p className="text-sm">{rec.message}</p>}
        </div>
      )}
      {rec && rec.notes.length > 0 && <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted">{rec.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      {rec && stressSummary(rec).length > 0 && (
        <ul className="space-y-0.5 text-sm">
          {stressSummary(rec).map((s) => <li key={s.variant}>{t("stress.summary", { variant: s.variant, breaks: s.breaks, runs: s.runs })}</li>)}
        </ul>
      )}

      {rec && rec.rows.length > 0 && (
        <div className="max-h-96 overflow-auto rounded-[8px] border border-border">
          <table className="w-full min-w-[40rem] border-collapse text-sm">
            <caption className="sr-only">{t("stress.title")}</caption>
            <thead className="sticky top-0 bg-surface-2">
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-2 py-2 font-medium">{t("stress.col_attack")}</th>
                <th scope="col" className="px-2 py-2 font-medium">{t("stress.col_variant")}</th>
                <th scope="col" className="px-2 py-2 text-right font-medium">{t("stress.col_seed")}</th>
                <th scope="col" className="px-2 py-2 text-right font-medium">{t("stress.col_evac")}</th>
                <th scope="col" className="px-2 py-2 text-right font-medium">{t("stress.col_peak")}</th>
                <th scope="col" className="px-2 py-2 font-medium">{t("stress.col_result")}</th>
                <th scope="col" className="px-2 py-2 font-medium">{t("stress.col_evidence")}</th>
              </tr>
            </thead>
            <tbody>
              {rec.rows.map((row, i) => {
                const o = rowOutcome(row);
                return (
                  <tr key={`${row.run_id ?? "x"}-${i}`} className={cn("border-t border-border align-top", o === "failed" && "bg-caution-soft/50")}>
                    <td className="px-2 py-1.5">{row.attack}</td>
                    <td className="px-2 py-1.5">{row.variant}</td>
                    <td className="px-2 py-1.5 text-right tabular">{t("stress.seed", { n: row.seed })}</td>
                    <td className="px-2 py-1.5 text-right tabular">{o === "breaks" || o === "holds" ? metricText("evac_time_95_s", row.metrics) : "–"}</td>
                    <td className="px-2 py-1.5 text-right tabular">{o === "breaks" || o === "holds" ? metricText("peak_density_ppm2", row.metrics) : "–"}</td>
                    <td className="px-2 py-1.5"><Badge tone={OUTCOME_TONE[o]}>{t(`stress.${o}`)}</Badge></td>
                    <td className="px-2 py-1.5 text-xs text-muted">{rowEvidence(row, rec.tier)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {failed.length > 0 && (
        <div className="space-y-1">
          <h3 className="text-sm font-medium">{t("stress.failures")}</h3>
          <ul className="space-y-0.5 text-xs">
            {failed.map((f, i) => <li key={`${f.run_id ?? "x"}-${i}`}>{f.attack} · {f.variant} · {t("stress.seed", { n: f.seed })}: <span className="text-muted">{f.error}</span></li>)}
          </ul>
        </div>
      )}
      {!rec && !stress.isLoading && <p className="text-sm text-muted">{t("stress.none")}</p>}
    </section>
  );
}
