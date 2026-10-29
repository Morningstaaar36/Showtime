import { Info } from "lucide-react";
import type * as React from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { RunResult } from "@/api/types";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { fmtClock, fmtNum } from "@/lib/format";
import { DENSITY_MAX } from "@/replay/density";
import { cn } from "@/lib/utils";
import { tierLabel } from "./verdict";
import { t } from "@/i18n";

export function MetricTile({ label, value, unit, tone = "neutral", run, formula, sub }: {
  label: string; value: string; unit?: string; tone?: "neutral" | "egress" | "caution" | "danger";
  run?: RunResult | null; formula: string; sub?: React.ReactNode;
}) {
  const bar = tone === "danger" ? "bg-danger" : tone === "caution" ? "bg-caution" : tone === "egress" ? "bg-egress" : "bg-line/50";
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className="group relative overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface p-3 text-left transition hover:border-border-strong">
          <span className={cn("absolute inset-y-0 left-0 w-[3px]", bar)} aria-hidden />
          <span className="flex items-center justify-between gap-1 text-xs text-muted">
            {label}<Info className="size-3.5 opacity-0 transition group-hover:opacity-100" />
          </span>
          <span className="mt-1 block text-xl font-semibold leading-tight tracking-tight tabular">
            {value}{unit && <span className="ml-1 text-sm font-normal text-muted">{unit}</span>}
          </span>
          {sub && <span className="mt-0.5 block text-xs text-muted">{sub}</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 text-sm">
        <p className="font-semibold">{label}</p>
        <dl className="mt-2 space-y-1.5 text-xs">
          <div><dt className="text-muted">{t("ui.metrics.source")}</dt><dd>{run ? tierLabel(run) : "–"}</dd></div>
          {run && <div><dt className="text-muted">{t("ui.metrics.engine_seed")}</dt><dd className="tabular">{run.engine} · {run.seed} · {run.provider}</dd></div>}
          <div><dt className="text-muted">{t("ui.metrics.how_its_computed")}</dt><dd>{formula}</dd></div>
        </dl>
      </PopoverContent>
    </Popover>
  );
}

const axis = { fontSize: 11, fill: "var(--muted)" };

/** People still inside over time (from the trajectory frame counts). */
export function EvacuationCurve({ times, counts, p95 }: { times: number[]; counts: number[]; p95: number | null | undefined }) {
  const step = Math.max(1, Math.floor(times.length / 240));
  const data = times.filter((_, i) => i % step === 0).map((tt, i) => ({ t: tt, n: counts[i * step] }));
  const text = t("ui.metrics.inside_fall", { from: counts[0]?.toLocaleString() ?? 0, to: counts[counts.length - 1]?.toLocaleString() ?? 0, time: fmtClock(times[times.length - 1]) });
  return (
    <figure>
      <figcaption className="sr-only">{text}</figcaption>
      <div className="h-36">
        <ResponsiveContainer>
          <AreaChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="inside" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--signal)" stopOpacity={0.35} />
                <stop offset="100%" stopColor="var(--signal)" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="t" tickFormatter={(v: number) => fmtClock(v)} tick={axis} stroke="var(--border)" minTickGap={30} />
            <YAxis tick={axis} stroke="var(--border)" width={40} />
            <Tooltip formatter={(v) => [Number(v).toLocaleString(), t("ui.metrics.inside")]} labelFormatter={(v) => fmtClock(Number(v))}
                     contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
            {p95 != null && <ReferenceLine x={p95} stroke="var(--egress)" strokeDasharray="4 3" label={{ value: t("metrics.p95_out"), fontSize: 10, fill: "var(--egress)", position: "insideTopRight" }} />}
            <Area type="monotone" dataKey="n" stroke="var(--signal)" strokeWidth={1.8} fill="url(#inside)" isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

/** Highest density anywhere over time, with warning and danger lines. */
export function DensityCurve({ series, duration, warn, danger }: { series: number[]; duration: number; warn: number; danger: number }) {
  const dt = series.length > 1 ? duration / (series.length - 1) : 1;
  const data = series.map((d, i) => ({ t: i * dt, d }));
  const peak = Math.max(0, ...series);
  // even steps up to the top of the scale (Recharts' own ticks for 0..7 read 0, 2, 4, 7)
  const top = Math.max(DENSITY_MAX, Math.ceil(peak));
  const step = top <= 8 ? 1 : Math.ceil(top / 8);
  const yTicks = Array.from({ length: Math.floor(top / step) + 1 }, (_, i) => i * step);
  return (
    <figure>
      <figcaption className="sr-only">{t("ui.metrics.peak_over_time", { ppm2: fmtNum(peak, 1) })}</figcaption>
      <div className="h-32">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="t" tickFormatter={(v: number) => fmtClock(v)} tick={axis} stroke="var(--border)" minTickGap={30} />
            <YAxis tick={axis} stroke="var(--border)" width={40} domain={[0, top]} ticks={yTicks} />
            <Tooltip formatter={(v) => [t("units.density", { n: fmtNum(Number(v), 1) }), t("ui.metrics.peak")]} labelFormatter={(v) => fmtClock(Number(v))}
                     contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
            <ReferenceLine y={warn} stroke="var(--caution)" strokeDasharray="4 3" />
            <ReferenceLine y={danger} stroke="var(--danger)" strokeDasharray="4 3" label={{ value: t("ui.metrics.danger_line"), fontSize: 10, fill: "var(--danger)", position: "insideTopLeft" }} />
            <Line type="monotone" dataKey="d" stroke="var(--ink)" strokeWidth={1.6} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

/** Horizontal bars: people per exit and mean flow. */
export function ExitUse({ run, label }: { run: RunResult; label: (id: string) => string }) {
  const rows = run.metrics?.per_exit ?? [];
  const max = Math.max(1, ...rows.map((r) => r.people));
  return (
    <ul className="space-y-2">
      {rows.map((r) => (
        <li key={r.exit_id} className="text-sm">
          <div className="flex justify-between gap-2">
            <span className="truncate">{label(r.exit_id)}</span>
            <span className="shrink-0 tabular text-muted">{r.people.toLocaleString()} · {t("units.n_per_s", { n: fmtNum(r.mean_flow_pps, 1) })}</span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-3">
            <div className={cn("h-full rounded-full", r.people === 0 ? "bg-line" : "bg-egress")} style={{ width: `${(r.people / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
