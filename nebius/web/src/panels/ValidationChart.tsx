/** Simulator check: flow through a bottleneck vs its width, real people against the simulator.
 * Measured points (one experiment run per width) over the simulated median with its min–max band. */
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { SimulatorValidation } from "@/api/types";
import { t } from "@/i18n";

interface ValidationRow {
  b: number;
  measured: number;
  median: number;
  range: [number, number];
  error: number;
}

export function validationRows(v: SimulatorValidation): ValidationRow[] {
  return [...v.widths]
    .sort((a, b) => a.b_m - b.b_m)
    .map((w) => ({
      b: w.b_m,
      measured: w.measured_flow_ps,
      median: w.simulated_flow_ps.median,
      range: [w.simulated_flow_ps.min, w.simulated_flow_ps.max],
      error: w.error_pct,
    }));
}

const f2 = (x: number) => x.toFixed(2);

function Tip({ active, payload }: { active?: boolean; payload?: { payload: ValidationRow }[] }) {
  const row = active ? payload?.[0]?.payload : undefined;
  if (!row) return null;
  return (
    <div className="rounded-[var(--radius-control)] border border-border bg-surface px-3 py-2 text-xs shadow-md">
      <p className="font-semibold">{t("validation.tip_width", { b: row.b })}</p>
      <p className="mt-1 flex items-center gap-2"><span aria-hidden className="size-2.5 rounded-full bg-orange" />{t("validation.tip_measured", { v: f2(row.measured) })}</p>
      <p className="flex items-center gap-2"><span aria-hidden className="h-0.5 w-3 bg-signal" />{t("validation.tip_sim", { v: f2(row.median), lo: f2(row.range[0]), hi: f2(row.range[1]) })}</p>
      <p className="mt-1 text-muted">{t("validation.tip_error", { e: `${row.error > 0 ? "+" : ""}${row.error.toFixed(0)}` })}</p>
    </div>
  );
}

/** `width` renders at a fixed size (tests, print); otherwise the chart fills its container. */
export function ValidationChart({ data, width }: { data: SimulatorValidation; width?: number }) {
  const rows = validationRows(data);
  const top = Math.ceil(Math.max(...rows.map((r) => Math.max(r.measured, r.range[1]))) + 0.5);
  const chart = (
    <ComposedChart data={rows} width={width} height={width ? 300 : undefined} margin={{ top: 8, right: 12, bottom: 18, left: 0 }}>
      <CartesianGrid stroke="var(--border)" strokeDasharray="0" vertical={false} />
      <XAxis dataKey="b" type="number" domain={[0.8, 2.6]} ticks={rows.map((r) => r.b)} tickFormatter={(b: number) => b.toFixed(1)}
             tick={{ fontSize: 11, fill: "var(--muted)" }} stroke="var(--line)"
             label={{ value: t("validation.axis_x"), position: "insideBottom", offset: -10, fontSize: 12, fill: "var(--muted)" }} />
      <YAxis domain={[0, top]} allowDecimals={false} tick={{ fontSize: 11, fill: "var(--muted)" }} stroke="var(--line)" width={40}
             label={{ value: t("validation.axis_y"), angle: -90, position: "insideLeft", offset: 10, dy: 60, fontSize: 12, fill: "var(--muted)" }} />
      <Tooltip content={<Tip />} cursor={{ stroke: "var(--line)" }} />
      <Area dataKey="range" stroke="none" fill="var(--signal)" fillOpacity={0.16} isAnimationActive={false} name={t("validation.legend_band")} />
      <Line dataKey="median" stroke="var(--signal)" strokeWidth={2} dot={{ r: 3, fill: "var(--signal)", stroke: "var(--surface)", strokeWidth: 2 }}
            isAnimationActive={false} name={t("validation.legend_sim")} />
      <Scatter dataKey="measured" fill="var(--orange)" stroke="var(--surface)" strokeWidth={2} shape="circle" isAnimationActive={false}
               name={t("validation.legend_measured")} />
    </ComposedChart>
  );
  return (
    <figure className="m-0">
      <ul className="mb-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted" aria-label={t("validation.legend")}>
        <li className="flex items-center gap-2"><span aria-hidden className="size-3 rounded-full border-2 border-surface bg-orange ring-1 ring-orange" />{t("validation.legend_measured")}</li>
        <li className="flex items-center gap-2"><span aria-hidden className="relative h-3 w-5 rounded-sm bg-signal/20"><span className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 bg-signal" /></span>{t("validation.legend_sim", { seeds: data.meta.seeds.length })}</li>
      </ul>
      <div className="h-[300px] w-full" data-testid="validation-chart" role="img"
           aria-label={t("validation.chart_label", { median: data.median_abs_error_pct.toFixed(0) })}>
        {width ? chart : <ResponsiveContainer>{chart}</ResponsiveContainer>}
      </div>
    </figure>
  );
}

/** The same numbers as a table (the chart's accessible alternative). */
export function ValidationTable({ data }: { data: SimulatorValidation }) {
  return (
    <table className="w-full text-sm tabular">
      <caption className="sr-only">{t("validation.table_caption")}</caption>
      <thead>
        <tr className="border-b border-border text-left text-muted">
          <th scope="col" className="py-1.5 pr-3 font-medium">{t("validation.col_width")}</th>
          <th scope="col" className="py-1.5 pr-3 font-medium">{t("validation.col_people")}</th>
          <th scope="col" className="py-1.5 pr-3 font-medium">{t("validation.col_measured")}</th>
          <th scope="col" className="py-1.5 pr-3 font-medium">{t("validation.col_sim")}</th>
          <th scope="col" className="py-1.5 font-medium">{t("validation.col_error")}</th>
        </tr>
      </thead>
      <tbody>
        {[...data.widths].sort((a, b) => a.b_m - b.b_m).map((w) => (
          <tr key={w.run_name} className="border-b border-border last:border-0">
            <td className="py-1.5 pr-3">{t("units.n_m", { n: w.b_m.toFixed(1) })}</td>
            <td className="py-1.5 pr-3">{w.n_people}</td>
            <td className="py-1.5 pr-3">{t("validation.per_s", { n: f2(w.measured_flow_ps) })}</td>
            <td className="py-1.5 pr-3">{t("validation.per_s", { n: f2(w.simulated_flow_ps.median) })} <span className="text-muted">({f2(w.simulated_flow_ps.min)}–{f2(w.simulated_flow_ps.max)})</span></td>
            <td className="py-1.5">{w.error_pct > 0 ? "+" : ""}{w.error_pct.toFixed(0)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
