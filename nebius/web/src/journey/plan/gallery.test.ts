import { describe, expect, it } from "vitest";
import type { Attack } from "@/api/types";
import { scenarioHeadline, scenarioKind, stressByAttack } from "./gallery";
import type { StressRecord } from "./stress";

const atk = (events: Record<string, unknown>[], title = "A long attack title with many words in it") => ({ title, events } as unknown as Attack);
const name = (id: string) => ({ door_e: "East exit", z1: "Ward A" })[id] ?? id;

describe("scenario cards", () => {
  it("names a scenario by what it does, in at most five words", () => {
    expect(scenarioHeadline(atk([{ type: "block_exit", exit_id: "door_e", at_s: 30 }]), name)).toBe("East exit blocked");
    expect(scenarioHeadline(atk([{ type: "surge", zone_id: "z1", extra_people: 50 }]), name)).toBe("Surge into Ward A");
    expect(scenarioHeadline(atk([{ type: "weird" }]), name).split(" ")).toHaveLength(5);
    expect(scenarioHeadline(null, name)).toBe("Everyone leaves normally");
  });
  it("picks the icon kind from the first event that makes it a scenario", () => {
    expect(scenarioKind(atk([{ type: "one_way" }, { type: "counterflow" }]))).toBe("counter");
    expect(scenarioKind(atk([]))).toBe("other");
    expect(scenarioKind(null)).toBe("normal");
  });
  it("counts finished stress runs per attack, without the single-change variants", () => {
    const row = (attack_id: string, breaks: boolean, extra: Record<string, unknown> = {}) =>
      ({ attack_id, breaks, status: "ok", fix_id: null, ...extra });
    const rec = { rows: [row("a", true), row("a", false), row("a", true, { fix_id: "f1" }), row("b", false, { status: "failed" })] } as unknown as StressRecord;
    const m = stressByAttack(rec);
    expect(m.get("a")).toEqual({ runs: 2, breaks: 1 });
    expect(m.has("b")).toBe(false);
  });
});
