/** Words for the seed check: "95% out in 4 min 29 s – 4 min 42 s over 4 seeds". */
import type { SeedCheck, SeedSpread } from "@/api/types";
import { t } from "@/i18n";
import { fmtDuration, fmtInt, fmtNum } from "@/lib/format";

const span = (s: SeedSpread, f: (v: number) => string) => (f(s.min) === f(s.max) ? f(s.min) : `${f(s.min)} – ${f(s.max)}`);

/** The range sentences, or null before any run finished. */
export function seedRangeLines(check: SeedCheck | null | undefined): string[] | null {
  const r = check?.range;
  if (!r) return null;
  const lines: string[] = [];
  const evac = r.evac_time_p95_s;
  if (evac) lines.push(t("seeds.range_evac", { range: span(evac, fmtDuration), n: evac.n }));
  const peak = r.peak_density_ppm2;
  if (peak) lines.push(t("seeds.range_peak", { range: span(peak, (v) => fmtNum(v, 1)), n: peak.n }));
  const inside = r.agents_not_evacuated;
  if (inside) lines.push(inside.max === 0 ? t("seeds.range_all_out", { n: inside.n }) : t("seeds.range_inside", { range: span(inside, fmtInt), n: inside.n }));
  return lines;
}

/** "3 × full simulation · 1 × quick simulation": what the range is based on. */
export function seedBasesText(check: SeedCheck | null | undefined, label: (basis: string) => string): string {
  return Object.entries(check?.bases ?? {}).map(([b, n]) => `${n} × ${label(b).toLowerCase()}`).join(" · ");
}
