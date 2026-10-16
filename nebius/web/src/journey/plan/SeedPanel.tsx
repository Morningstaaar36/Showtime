/** "Check with more seeds" on Your plan (S-09): repeats the run the verdict rests on with other
 * random crowds and shows the range, with each run's basis. */
import { Dices } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useSeedCheck, useStartSeedCheck } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/input";
import { Progress, Spinner } from "@/components/ui/misc";
import { t } from "@/i18n";
import { basisLabel } from "@/lib/evidence";
import { fmtDuration, fmtInt, fmtNum } from "@/lib/format";
import { seedBasesText, seedRangeLines } from "./seeds";

export function SeedPanel({ sessionId, human = (s) => s }: { sessionId: string; human?: (s: string) => string }) {
  const check = useSeedCheck(sessionId);
  const start = useStartSeedCheck(sessionId);
  const [n, setN] = useState<number | null>(null);
  const d = check.data;
  if (!d) return null;
  const running = d.status === "running" || start.isPending;
  const lines = seedRangeLines(d);
  const count = n ?? d.default_extra;
  return (
    <section aria-labelledby="seeds-h" className="space-y-3 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm" data-testid="seed-check">
      <div>
        <h2 id="seeds-h" className="flex items-center gap-2 font-semibold"><Dices className="size-4 text-signal" aria-hidden />{t("seeds.title")}</h2>
        <p className="max-w-prose text-sm text-muted">{t("seeds.lead")}</p>
        {d.key && <p className="mt-1 text-xs text-muted">{t("seeds.repeats", { label: human(d.key.label) })}</p>}
      </div>

      {!d.available ? <p className="text-sm text-muted">{t("seeds.unavailable", { reason: d.reason ?? "" })}</p> : (
        <div className="flex flex-wrap items-end gap-3">
          <div className="grid gap-1">
            <Label htmlFor="seed-n" className="text-sm text-muted">{t("seeds.how_many")}</Label>
            <select id="seed-n" value={count} disabled={running} onChange={(e) => setN(Number(e.target.value))}
                    className="h-10 rounded-[var(--radius-control)] border border-border bg-surface px-2 text-base">
              {Array.from({ length: d.max_extra }, (_, i) => i + 1).map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
          <Button variant={d.status === "none" ? "primary" : "secondary"} disabled={running}
                  onClick={() => start.mutate(count, { onError: (e) => toast.error(e.message) })}>
            {running ? <Spinner /> : <Dices />}{t(d.status === "none" ? "seeds.start" : "seeds.again")}
          </Button>
        </div>
      )}

      {d.status === "running" && (
        <div className="space-y-1" aria-live="polite">
          <p className="text-sm">{t("seeds.running", { done: d.done, total: d.total })}</p>
          <Progress value={d.total ? (d.done / d.total) * 100 : 0} />
        </div>
      )}

      {lines && lines.length > 0 && (
        <div className="space-y-1 rounded-[10px] bg-surface-2 p-3" aria-live="polite">
          {lines.map((l) => <p key={l} className="text-sm font-semibold tabular">{l}</p>)}
          <p className="text-xs text-muted">{t("seeds.based_on", { bases: seedBasesText(d, basisLabel) })}</p>
          {d.notes.map((x) => <p key={x} className="text-xs text-muted">{x}</p>)}
        </div>
      )}

      {d.items.length > 0 && (
        <details className="rounded-[10px] border border-border text-sm">
          <summary className="flex min-h-11 cursor-pointer items-center px-3 font-medium">{t("seeds.runs")}</summary>
          <ul className="divide-y divide-border border-t border-border">
            {d.items.map((it) => (
              <li key={`${it.seed}:${it.run_id}`} className="flex flex-wrap items-baseline justify-between gap-2 px-3 py-2">
                <span className="font-medium tabular">{t("seeds.seed", { seed: it.seed })}{it.original ? ` · ${t("seeds.original")}` : ""}</span>
                <span className="text-xs text-muted tabular">
                  {it.metrics ? t("seeds.run_line", {
                    evac: fmtDuration(it.metrics.evac_time_p95_s), peak: fmtNum(it.metrics.peak_density_ppm2, 1), inside: fmtInt(it.metrics.agents_not_evacuated),
                  }) : it.status}
                </span>
                <Badge tone={it.included ? "neutral" : "outline"}>{basisLabel(it.basis, it.tier ?? undefined)}</Badge>
              </li>
            ))}
          </ul>
        </details>
      )}
      {d.status === "none" && d.available && <p className="text-xs text-muted">{t("seeds.none")}</p>}
    </section>
  );
}
