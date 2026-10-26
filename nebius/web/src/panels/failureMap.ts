/** Pure helpers for the failure map (the red team's quality-diversity archive, docs/RAINBOW.md). */
import type { FailureMap, FailureMapCell, FailureMapElite } from "@/types/generated";
import { t } from "@/i18n";

export type { FailureMap, FailureMapCell, FailureMapElite };

/** How a cell reads: no attack yet, holds, close to breaking, breaks the plan. */
export type Tone = "empty" | "holds" | "near" | "break";

/** Severity at or above this is "close": 70% of the way to a break. */
export const NEAR = 0.7;

/** Severity on the plan as it stands: after a kept fix, its re-measured value. */
export function current(e: FailureMapElite): number {
  return e.severity_after ?? e.severity;
}

/** The cell's strongest attack on the current plan. */
export function best(cell: FailureMapCell | null | undefined): FailureMapElite | null {
  if (!cell || !cell.elites.length) return null;
  return cell.elites.reduce((a, b) => (current(b) > current(a) ? b : a));
}

export function tone(sev: number | null | undefined): Tone {
  if (sev == null) return "empty";
  if (sev >= 1) return "break";
  if (sev >= NEAR) return "near";
  return "holds";
}

export const toneLabel = (tone: Tone) => t(`failure_map.tone_${tone}`);

export interface GridRow { id: string; label: string; cells: (FailureMapCell | null)[] }
export interface Grid { cols: FailureMap["wheres"]; rows: GridRow[] }

/** Rows = hazard kinds, columns = places; a null cell is not possible in this venue (e.g. a
 *  blocked exit on a floor without exits). Rows and columns without any possible cell go. */
export function buildGrid(map: FailureMap): Grid {
  const at = new Map(map.cells.map((c) => [`${c.kind}|${c.where}`, c]));
  const cols = map.wheres.filter((w) => map.cells.some((c) => c.where === w.id));
  const rows = map.kinds
    .filter((k) => map.cells.some((c) => c.kind === k.id))
    .map((k) => ({ id: k.id, label: k.label, cells: cols.map((w) => at.get(`${k.id}|${w.id}`) ?? null) }));
  return { cols, rows };
}

export function fmtCoverage(map: Pick<FailureMap, "coverage">): string {
  return `${Math.round(map.coverage * 100)}%`;
}

export function fmtSeverity(sev: number | null | undefined): string {
  return sev == null ? "—" : sev.toFixed(2);
}

/** Coverage and QD-score per round, oldest first ("Round 1: 29% · 4.20"). */
export function historyLine(map: FailureMap): string {
  return map.history.map((h) => t("failure_map.round", { n: h.round, pct: Math.round(h.coverage * 100), qd: h.qd_score.toFixed(2) })).join(" → ");
}


/** "Exit blocked · Near West stairwell" for an attack's cell, or null without a map. */
export function cellLabel(map: FailureMap | null | undefined, cell: { kind: string; where: string } | null | undefined): string | null {
  if (!map || !cell) return null;
  const k = map.kinds.find((x) => x.id === cell.kind)?.label ?? cell.kind;
  const w = map.wheres.find((x) => x.id === cell.where)?.label ?? cell.where;
  return `${k} · ${w}`;
}
