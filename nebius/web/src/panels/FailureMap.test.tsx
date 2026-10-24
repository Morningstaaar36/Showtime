import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EMPTY, reduce } from "@/api/useSessionStream";
import type { SessionEvent } from "@/types/generated";
import { FailureMap as FailureMapView } from "./FailureMap";
import { best, buildGrid, cellLabel, current, type FailureMap, fmtCoverage, historyLine, tone } from "./failureMap";

const elite = (id: string, severity: number, extra: Partial<FailureMap["cells"][number]["elites"][number]> = {}) => ({
  attack_id: id, title: `Attack ${id}`, run_id: `r_${id}`, severity, is_break: severity >= 1, round: 1, metrics: {}, parts: {},
  basis: "simulation", generated_by: "ai", fixed_by: null, severity_after: null, after_run_id: null, ...extra,
});

const MAP: FailureMap = {
  method: "map_elites", per_cell: 2,
  kinds: [{ id: "exit_blocked", label: "Exit blocked" }, { id: "surge", label: "Surge" }, { id: "route_change", label: "Wrong route" }],
  wheres: [{ id: "floor:F0", label: "Ground floor", exits: ["d1"], zones: ["a"] }, { id: "floor:F1", label: "Mezzanine", exits: [], zones: ["m"] },
    { id: "all", label: "Whole venue", exits: ["d1"], zones: ["a", "m"] }],
  cells: [
    { kind: "exit_blocked", where: "floor:F0", elites: [elite("A1", 0.5), elite("A2", 1.4)] },
    { kind: "surge", where: "floor:F0", elites: [] },
    { kind: "surge", where: "floor:F1", elites: [elite("A3", 0.8, { fixed_by: "F1", severity_after: 0.2 })] },
  ],
  cells_total: 3, filled: 2, coverage: 0.667, qd_score: 2.7, open_breaks: 1, aim: { targeted: 3, hit: 2 },
  history: [{ round: 1, coverage: 0.333, qd_score: 1.9, filled: 1 }, { round: 2, coverage: 0.667, qd_score: 2.7, filled: 2 }],
  fitness: "severity = max(...)",
};

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let cleanup: (() => void) | null = null;
afterEach(() => cleanup?.());

function render(node: React.ReactNode): HTMLElement {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => root.render(node));
  cleanup = () => { act(() => root.unmount()); el.remove(); };
  return el;
}

describe("failure map", () => {
  it("lays out kinds × places, leaving impossible cells null and dropping empty axes", () => {
    const g = buildGrid(MAP);
    expect(g.rows.map((r) => r.id)).toEqual(["exit_blocked", "surge"]);
    expect(g.cols.map((c) => c.id)).toEqual(["floor:F0", "floor:F1"]);
    expect(g.rows[0].cells[1]).toBeNull();
    expect(g.rows[1].cells[0]?.elites).toEqual([]);
  });

  it("reads a cell by its strongest attack on the current plan", () => {
    expect(best(MAP.cells[0])?.attack_id).toBe("A2");
    expect(best(MAP.cells[1])).toBeNull();
    const fixed = MAP.cells[2].elites[0];
    expect(current(fixed)).toBe(0.2);
    expect([tone(null), tone(0.2), tone(0.7), tone(0.99), tone(1)]).toEqual(["empty", "holds", "near", "near", "break"]);
  });

  it("formats coverage, history and cell names", () => {
    expect(fmtCoverage(MAP)).toBe("67%");
    expect(historyLine(MAP)).toBe("Round 1: 33% · 1.90 → Round 2: 67% · 2.70");
    expect(cellLabel(MAP, { kind: "surge", where: "floor:F1" })).toBe("Surge · Mezzanine");
    expect(cellLabel(null, { kind: "surge", where: "x" })).toBeNull();
  });

  it("folds archive events from the session stream", () => {
    const ev = (seq: number, type: SessionEvent["type"], payload: Record<string, unknown>) => ({ kind: "event" as const, ev: { seq, type, ts: "t", payload } });
    let s = reduce(EMPTY, ev(1, "archive", { round: 1, change: null, archive: MAP }));
    expect(s.archive?.filled).toBe(2);
    s = reduce(s, ev(2, "archive", { round: 1, change: null }));
    expect(s.archive?.filled).toBe(2);
    s = reduce(s, ev(3, "attack_card", { round: 1, attack: { attack_id: "A9" }, tier1: {}, cell: { kind: "surge", where: "floor:F0" } }));
    expect(s.attacks[0].cell).toEqual({ kind: "surge", where: "floor:F0" });
  });

  it("shows coverage and total severity; a picked cell shows its attacks, whose buttons play them", () => {
    const onSelectRun = vi.fn();
    const el = render(<FailureMapView map={MAP} onSelectRun={onSelectRun} />);
    expect(el.textContent).toContain("67%");
    expect(el.textContent).toContain("2.70");
    const cells = [...el.querySelectorAll<HTMLButtonElement>("tbody button")];
    expect(cells).toHaveLength(3);
    // colour is never the only signal: each cell names its state
    expect(cells[0].getAttribute("aria-label")).toContain("Breaks the plan");
    expect(cells[1].textContent).toContain("gap");
    act(() => cells[0].click());
    expect(onSelectRun).not.toHaveBeenCalled(); // picking a cell only shows what landed there
    expect(el.textContent).toContain("Attack A2");
    // each attack in the cell has its own button; A2's plays A2's run
    const block = [...el.querySelectorAll<HTMLElement>("div")].find((d) => d.firstElementChild?.textContent?.startsWith("Attack A2"));
    const show = [...(block?.querySelectorAll<HTMLButtonElement>("button") ?? [])].find((x) => x.textContent?.includes("Show attack"));
    act(() => show!.click());
    expect(onSelectRun).toHaveBeenCalledWith("r_A2");
  });
});
