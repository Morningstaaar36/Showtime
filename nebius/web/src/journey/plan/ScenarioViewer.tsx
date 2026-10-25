/** Your plan's scenario viewer: every tested scenario with its verdict (click to replay it), the
 * caption of what is happening in the replay, and people per floor over time. */
import { ExternalLink, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Attack } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { t } from "@/i18n";
import { ScriptCode } from "@/journey/ScriptCode";
import { fmtClock, fmtInt, fmtNum } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { TimelineMarker } from "@/panels/Timeline";
import type { Trajectory } from "@/replay/trajectory";
import { usePlayback } from "@/state/playback";
import { captionAt, type Outcome, peoplePerFloor, type ScenarioRow } from "./scenarios";

function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  if (outcome === "break") return <Badge tone="danger">{t("work.breaks")}</Badge>;
  if (outcome === "holds") return <Badge tone="egress">{t("work.holds")}</Badge>;
  if (outcome === "running") return <Badge tone="neutral">{t("yourplan.sc_running")}</Badge>;
  if (outcome === "failed") return <Badge tone="caution">{t("yourplan.sc_failed")}</Badge>;
  return <Badge tone="neutral">{t(outcome === "preview" ? "work.preview" : "work.unknown")}</Badge>;
}

function RowButton({ row, picked, onPick, nested }: { row: ScenarioRow; picked: boolean; onPick: (r: ScenarioRow) => void; nested?: boolean }) {
  const playable = row.outcome !== "running" && row.outcome !== "failed";
  return (
    <button type="button" aria-pressed={picked} disabled={!playable} onClick={() => onPick(row)}
            className={cn("flex min-h-11 w-full items-start gap-2 rounded-[8px] px-2.5 py-2 text-left text-sm transition disabled:cursor-default disabled:opacity-70",
                          picked ? "bg-signal-soft ring-2 ring-signal" : "hover:bg-surface-2", nested && "pl-6")}>
      <Play className={cn("mt-0.5 size-3.5 shrink-0", picked ? "text-signal" : "text-muted")} aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="block font-medium">{nested ? `${t("yourplan.sc_fix")}: ${row.title}` : row.title}</span>
        {row.evacS != null && (
          <span className="block text-xs text-muted tabular">
            {t("yourplan.sc_metrics", { evac: fmtClock(row.evacS), peak: row.peak != null ? fmtNum(row.peak, 1) : "–" })}
          </span>
        )}
      </span>
      <span className="flex shrink-0 flex-col items-end gap-1">
        <OutcomeBadge outcome={row.outcome} />
        {nested && row.accepted != null && <span className="text-2xs text-muted">{row.accepted ? t("yourplan.sc_kept") : t("yourplan.sc_not_kept")}</span>}
        {picked && <span className="text-2xs font-semibold text-signal">{t("yourplan.sc_playing")}</span>}
      </span>
    </button>
  );
}

export function ScenarioList({ rows, pickedRun, onPick, attacks }: {
  rows: ScenarioRow[]; pickedRun: string | null; onPick: (r: ScenarioRow) => void; attacks: Attack[];
}) {
  return (
    <section aria-labelledby="scenarios-h" className="space-y-2 rounded-[10px] border border-border bg-surface p-4" data-testid="scenarios">
      <div>
        <h2 id="scenarios-h" className="font-semibold">{t("yourplan.scenarios")}</h2>
        <p className="text-xs text-muted">{t("yourplan.scenarios_lead")}</p>
      </div>
      {rows.length === 0 ? <p className="text-sm text-muted">{t("yourplan.no_risks")}</p> : (
        <ul className="-mx-2.5 max-h-[28rem] space-y-0.5 overflow-y-auto scrollbar-thin">
          {rows.map((r) => {
            const a = r.kind === "attack" && !r.key.includes(":current:") ? attacks.find((x) => x.attack_id === r.attackId) : undefined;
            return (
              <li key={r.key}>
                <RowButton row={r} picked={pickedRun === r.runId} onPick={onPick} />
                {a?.inspired_by?.source_url && (
                  <a href={a.inspired_by.source_url} target="_blank" rel="noreferrer" className="ml-8 flex min-h-11 items-center gap-1 text-xs text-signal hover:underline">
                    <ExternalLink className="size-3" />{t("work.inspired_by", { what: `${a.inspired_by.incident}${a.inspired_by.year ? ` (${a.inspired_by.year})` : ""}` })}
                  </a>
                )}
                {a && <ScriptCode attack={a} className="ml-8" />}
                {r.children.length > 0 && (
                  <ul className="space-y-0.5">{r.children.map((c) => <li key={c.key}><RowButton row={c} nested picked={pickedRun === c.runId} onPick={onPick} /></li>)}</ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** "South door 1 blocked at 1:00" over the replay while it happens (and a few seconds after). */
export function ReplayCaption({ markers, className }: { markers: TimelineMarker[]; className?: string }) {
  const [now, setNow] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setNow(usePlayback.getState().t), 250);
    return () => window.clearInterval(id);
  }, []);
  const hit = captionAt(markers, now);
  return (
    <div aria-live="polite" className={cn("pointer-events-none", className)}>
      {hit && (
        <p className={cn("rounded-full px-3 py-1 text-sm font-semibold shadow-[var(--shadow-float)]",
                         hit.tone === "danger" ? "bg-danger-strong text-on-strong" : hit.tone === "caution" ? "bg-caution-strong text-on-strong" : hit.tone === "egress" ? "bg-egress-strong text-on-strong" : "bg-signal text-signal-ink")}>
          {hit.label}
        </p>
      )}
    </div>
  );
}

const FLOOR_COLORS = ["#1F5FBF", "#CC79A7", "#56B4E9", "#7E57C2", "#0072B2", "#8E9BA5", "#E8D44D", "#1C2329"];

/** People still on each floor over time (multi-storey replays), with a text summary.
 * `allOutS`: the run reports everyone out at that time; the last frame can still hold someone
 * stepping through an exit, so the curves end at zero then. */
export function FloorChart({ traj, floorName, allOutS = null }: { traj: Trajectory; floorName: (id: string) => string; allOutS?: number | null }) {
  const series = useMemo(() => {
    const s = peoplePerFloor(traj);
    const lastT = s.times[s.times.length - 1];
    if (allOutS == null || lastT == null || s.counts.every((c) => !c[c.length - 1])) return s;
    return { ...s, times: [...s.times, Math.max(allOutS, lastT)], counts: s.counts.map((c) => [...c, 0]) };
  }, [traj, allOutS]);
  const data = useMemo(() => series.times.map((tm, i) => ({
    t: tm, ...Object.fromEntries(series.floors.map((f, j) => [f, series.counts[j][i]])),
  })), [series]);
  if (series.floors.length < 2) return null;
  const summary = series.floors.map((f, j) => t("yourplan.per_floor_summary", {
    floor: floorName(f), start: fmtInt(series.counts[j][0] ?? 0), end: fmtInt(series.counts[j][series.counts[j].length - 1] ?? 0),
  })).join(" ");
  return (
    <section aria-labelledby="perfloor-h" className="space-y-2 rounded-[10px] border border-border bg-surface p-4" data-testid="per-floor">
      <div>
        <h2 id="perfloor-h" className="font-semibold">{t("yourplan.per_floor")}</h2>
        <p className="text-xs text-muted">{t("yourplan.per_floor_lead")}</p>
      </div>
      <div className="h-48" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey="t" type="number" domain={[0, "dataMax"]} tickFormatter={(v: number) => fmtClock(v)} tick={{ fontSize: 11 }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
            <Tooltip labelFormatter={(v) => fmtClock(Number(v))} formatter={(v, k) => [fmtInt(Number(v)), floorName(String(k))]} />
            <Legend formatter={(k) => floorName(String(k))} wrapperStyle={{ fontSize: 12 }} />
            {series.floors.map((f, j) => (
              <Line key={f} dataKey={f} type="monotone" dot={false} strokeWidth={2} stroke={FLOOR_COLORS[j % FLOOR_COLORS.length]}
                    strokeDasharray={j % 2 ? "5 3" : undefined} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-muted">{summary}</p>
    </section>
  );
}
