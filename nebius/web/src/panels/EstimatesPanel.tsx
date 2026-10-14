import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Users } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { usePatchProject } from "@/api/queries";
import type { Estimates, PatchOpIn, ProjectDetail } from "@/api/types";
import { Spinner } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { t } from "@/i18n";
import { fmtInt } from "@/lib/format";
import { cn } from "@/lib/utils";

const HOURS = [2, 4, 6, 8, 12, 24];

/** Estimates for the day: safe capacity, exits, staff, toilets, fencing and a budget, each with its source.
 * Shown in the "Plan for the day" card of the Plan inspector. */
export function EstimatesPanel({ project }: { project: ProjectDetail }) {
  const version = project.version.version;
  const q = useQuery({
    queryKey: ["estimates", project.id, version],
    queryFn: () => api.get<Estimates>(`/projects/${project.id}/estimates?version=${version}`),
    staleTime: 60_000,
  });
  const patch = usePatchProject(project.id);
  const setEvent = (fields: Record<string, unknown>, msg: string) =>
    patch.mutate({ patch: { ops: [{ op: "set_event", ...fields } as unknown as PatchOpIn] }, message: msg },
      { onError: (e) => toast.error(e.message) });
  const est = q.data;
  if (!est) return q.isLoading ? <Spinner /> : <p className="text-sm text-muted">{t("workspace.estimates_unavailable")}</p>;
  const cap = est.capacity;
  const over = cap.current_people > cap.safe_people;
  const pct = Math.min(100, (cap.current_people / Math.max(cap.safe_people, 1)) * 100);
  const money = (v: number) => `${est.currency} ${fmtInt(Math.round(v))}`;
  return (
    <div className="space-y-3">

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <label className="inline-flex items-center gap-1.5">
          <span className="text-muted">Open for</span>
          <select className="h-7 rounded-[var(--radius-control)] border border-border bg-surface px-1.5 tabular"
                  value={est.event.duration_h}
                  onChange={(e) => setEvent({ duration_h: Number(e.target.value) }, `Event open ${e.target.value} h`)}>
            {[...new Set([...HOURS, est.event.duration_h])].sort((a, b) => a - b).map((h) => <option key={h} value={h}>{h} h</option>)}
          </select>
        </label>
        <label className="inline-flex items-center gap-1.5">
          <Switch checked={!!est.event.alcohol} onCheckedChange={(v) => setEvent({ alcohol: v }, v ? "Alcohol served" : "No alcohol")} aria-label="Alcohol served" />
          <span>Alcohol</span>
        </label>
        <div className="inline-flex rounded-[var(--radius-control)] border border-border p-0.5">
          {(["standing", "seated", "mixed"] as const).map((a) => (
            <button key={a} type="button" onClick={() => setEvent({ audience: a }, `Audience ${a}`)}
                    className={cn("rounded-[4px] px-2 py-0.5 capitalize", est.event.audience === a ? "bg-signal text-signal-ink" : "text-muted hover:text-ink")}>
              {a}
            </button>
          ))}
        </div>
      </div>

      <div className={cn("rounded-[10px] border p-3", over ? "border-caution/50 bg-caution-soft/60" : "border-egress/30 bg-egress-soft/50")}>
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="text-xs text-muted">Safe capacity</p>
            <p className="text-2xl font-semibold tabular leading-tight">{fmtInt(cap.safe_people)} <span className="text-sm font-normal text-muted">people</span></p>
          </div>
          <p className="text-right text-xs"><Users className="mr-1 inline size-3.5" />you plan <b className="tabular">{fmtInt(cap.current_people)}</b></p>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-border" aria-hidden>
          <div className={cn("h-full rounded-full", over ? "bg-caution" : "bg-egress")} style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-2 text-xs text-muted">
          Limited by <b className="text-ink">{{ exits: "exit width", stairs: "stair width", space: "floor space" }[cap.limited_by]}</b>. {cap.note}
        </p>
      </div>

      <ul className="divide-y divide-border rounded-[10px] border border-border">
        {est.lines.filter((l) => l.key !== "capacity").map((l) => (
          <li key={l.key} className="px-3 py-2">
            <div className="flex items-baseline justify-between gap-2">
              <span className={cn("text-sm", l.status === "warn" && "text-caution")}>{l.label}</span>
              <span className="tabular text-sm font-semibold">{fmtInt(l.value)} <span className="font-normal text-muted">{l.unit}</span></span>
            </div>
            <p className="mt-0.5 text-xs text-muted">
              {l.detail}{" "}
              {l.url ? <a href={l.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-signal hover:underline" title={l.source}>source<ExternalLink className="size-3" /></a>
                : <span title={l.source}>({l.source})</span>}
            </p>
          </li>
        ))}
      </ul>

      <details className="rounded-[10px] border border-border px-3 py-2 text-sm">
        <summary className="flex cursor-pointer items-baseline justify-between">
          <span>Budget estimate</span><span className="tabular font-semibold">{money(est.budget_total)}</span>
        </summary>
        <table className="mt-2 w-full text-xs">
          <tbody>
            {est.budget.map((b) => (
              <tr key={b.item} className="border-t border-border">
                <td className="py-1">{b.item}</td>
                <td className="py-1 text-right tabular text-muted">{fmtInt(b.quantity)} × {fmtInt(b.unit_cost)}</td>
                <td className="py-1 text-right tabular">{fmtInt(b.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-2xs text-muted">{est.prices_are_examples ? "Example unit prices: replace them with your quotes in Settings." : "Your unit prices from Settings."}</p>
      </details>
    </div>
  );
}
