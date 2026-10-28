import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, Loader2, Play } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { PanelTitle } from "@/components/ui/misc";
import { cn } from "@/lib/utils";
import { useUi } from "@/state/ui";
import { t } from "@/i18n";

interface Item {
  key: string; label: string; run_id: string | null; skipped?: string; status?: string; progress?: number | null;
  closed_exit?: string | null;
  metrics?: { evac_time_p95_s: number | null; peak_density_ppm2: number; time_above_danger_s: number; agents_not_evacuated: number; agents_total: number };
}
interface Sweep { version: number | null; tier?: number; items: Item[] }

const mmss = (s: number | null | undefined) => (s == null ? "—" : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`);

/** Six what-ifs simulated in parallel sandboxes; each card fills in as its sandbox finishes. */
export function ScenarioMatrix({ projectId, version, danger, warn }: { projectId: string; version: number; danger: number; warn: number }) {
  const qc = useQueryClient();
  const setActive = useUi((s) => s.setActiveRun);
  const active = useUi((s) => s.activeRunId);
  const q = useQuery({
    queryKey: ["sweep", projectId],
    queryFn: () => api.get<Sweep>(`/projects/${projectId}/sweep`),
    refetchInterval: (query) => (query.state.data?.items.some((i) => i.status === "running" || i.status === "queued") ? 2500 : false),
  });
  const start = useMutation({
    mutationFn: () => api.post<Sweep>(`/projects/${projectId}/sweep`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["sweep", projectId] }); toast.success(t("ui.scenariomatrix.six_scenarios_queued_in_sandboxes")); },
    onError: (e) => toast.error(e.message),
  });
  const data = q.data;
  const stale = data?.version != null && data.version !== version;
  const running = data?.items.some((i) => i.status === "running" || i.status === "queued");
  return (
    <section className="space-y-2" aria-label={t("ui.scenariomatrix.scenario_sweep")}>
      <div className="flex items-center justify-between">
        <PanelTitle><Boxes className="mr-1.5 inline size-4 text-signal" />{t("ui.scenariomatrix.scenario_sweep")}</PanelTitle>
        <Button size="sm" variant="secondary" disabled={start.isPending || running} onClick={() => start.mutate()}>
          {start.isPending || running ? <Loader2 className="animate-spin" /> : <Play />}{data?.items.length ? t("ui.scenariomatrix.run_again") : t("ui.scenariomatrix.run_6_scenarios")}
        </Button>
      </div>
      <p className="text-xs text-muted">
        {t(data?.tier === 2 ? "ui.scenariomatrix.lead_partial" : "ui.scenariomatrix.lead")}
        {stale && ` ${t("ui.scenariomatrix.stale")}`}
      </p>
      {data && data.items.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {data.items.map((it) => {
            const m = it.metrics;
            const peak = m?.peak_density_ppm2 ?? 0;
            const tone = !m ? "border-border" : peak >= danger || (m.agents_not_evacuated > 0 && it.status === "ok") ? "border-danger/60 bg-danger-soft/40"
              : peak >= warn ? "border-caution/60 bg-caution-soft/40" : "border-egress/40 bg-egress-soft/40";
            return (
              <button key={it.key} type="button" disabled={!it.run_id || !m}
                      onClick={() => it.run_id && setActive(it.run_id)}
                      className={cn("rounded-[var(--radius-panel)] border p-2 text-left transition hover:shadow-[var(--shadow-float)] disabled:cursor-default",
                        tone, active && it.run_id === active && "ring-2 ring-signal")}>
                <p className="line-clamp-2 text-xs font-medium leading-snug">{it.label}</p>
                {it.closed_exit && <p className="text-2xs text-muted">{t("ui.scenariomatrix.closes", { exit: it.closed_exit })}</p>}
                {it.skipped ? <p className="mt-1 text-2xs text-muted">{it.skipped}</p>
                  : !m ? (
                    <div className="mt-2">
                      <div className="h-1 overflow-hidden rounded-full bg-border"><div className="h-full animate-pulse rounded-full bg-signal" style={{ width: `${Math.max(8, (it.progress ?? 0) * 100)}%` }} /></div>
                      <p className="mt-1 text-2xs capitalize text-muted">{it.status ?? t("ui.scenariomatrix.queued")}</p>
                    </div>
                  ) : (
                    <div className="mt-1.5 grid grid-cols-2 gap-x-2 text-2xs">
                      <span className="text-muted">{t("ui.scenariomatrix.95_out")}</span><span className="tabular text-right font-semibold">{mmss(m.evac_time_p95_s)}</span>
                      <span className="text-muted">{t("ui.scenariomatrix.peak_m")}</span><span className={cn("tabular text-right font-semibold", peak >= danger && "text-danger")}>{peak.toFixed(1)}</span>
                      <span className="text-muted">{t("ui.scenariomatrix.still_inside")}</span><span className="tabular text-right font-semibold">{m.agents_not_evacuated.toLocaleString()}</span>
                    </div>
                  )}
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
