import { describe, expect, it } from "vitest";
import { ApiError } from "@/api/client";
import type { AskIntent, AskWhatIf, WhatIfParams } from "@/api/queries";
import type { WhatIfOut } from "@/api/types";
import { askError, cappedNote, intentMeta, navAction, retryWithExit, whatIfChips, whatIfRows } from "@/journey/askModel";

const INTENTS: AskIntent[] = ["edit", "question", "what_if", "analyse", "navigate", "other"];

function estimate(people: number, evac: number | null, peak: number, safe: number, score: number, stuck = 0): WhatIfOut {
  return {
    metrics: { evac_time_p95_s: evac, peak_density_ppm2: peak, agents_not_evacuated: stuck },
    hotspots: [], lines: [], budget_total: 0, currency: "USD", basis: "Instant estimate (formula)", people,
    capacity: { safe_people: safe } as WhatIfOut["capacity"],
    score: { score, grade: "B", parts: [], capped: "", basis: "Instant estimate (formula)" },
  } as unknown as WhatIfOut; // only the fields the rows read
}

const PARAMS: WhatIfParams = {
  crowd_scale: 2, crowd_scale_asked: 2, capped: false, weather: "rain", speed_factor: 0.85,
  closed_exits: [{ id: "door_s1", name: "South door 1" }], changed: true,
};

describe("intentMeta", () => {
  it("gives every intent a label from the strings and its own icon and colour", () => {
    const metas = INTENTS.map(intentMeta);
    for (const m of metas) expect(m.label).not.toMatch(/^ask\./);
    expect(intentMeta("what_if").label).toBe("What if");
    expect(new Set(metas.map((m) => m.icon)).size).toBe(INTENTS.length);
    expect(new Set(metas.map((m) => m.tone)).size).toBe(INTENTS.length);
  });
});

describe("navAction", () => {
  it("opens the report of the session, else of the project, in a new tab", () => {
    expect(navAction("report", "p1", "s1")).toEqual({ kind: "open", href: "/api/v1/sessions/s1/report" });
    expect(navAction("report", "p1", null)).toEqual({ kind: "open", href: "/api/v1/projects/p1/report" });
  });

  it("goes to the screens of the project and keeps the session", () => {
    expect(navAction("expert", "p1", "s1")).toEqual({ kind: "route", to: "/p/p1/expert" });
    expect(navAction("check", "p1", "s1")).toEqual({ kind: "route", to: "/p/p1/describe" });
    expect(navAction("plan", "p1", "s1")).toEqual({ kind: "route", to: "/p/p1?session=s1" });
    expect(navAction("work", "p1")).toEqual({ kind: "route", to: "/p/p1/work" });
  });
});

describe("whatIfRows", () => {
  it("puts the plan as it is next to the what-if and flags what got worse", () => {
    const r: AskWhatIf = { ...estimate(2400, 300, 3.44, 2000, 52), before: estimate(1200, 200, 2.1, 2000, 78), params: PARAMS };
    const rows = Object.fromEntries(whatIfRows(r).map((x) => [x.key, x]));
    expect(rows.people).toMatchObject({ before: "1,200", after: "2,400", worse: false });
    expect(rows.evac).toMatchObject({ before: "3 min 20 s", after: "5 min", worse: true });
    expect(rows.peak).toMatchObject({ before: "2.1 per m²", after: "3.4 per m²", worse: true });
    expect(rows.capacity).toMatchObject({ before: "2,000", after: "2,000", worse: true });
    expect(rows.score).toMatchObject({ before: "78", after: "52", worse: true });
  });

  it("says how many are still inside when not everyone gets out", () => {
    const r: AskWhatIf = { ...estimate(1200, null, 2, 2000, 40, 35), before: estimate(1200, 200, 2, 2000, 78), params: PARAMS };
    const evac = whatIfRows(r).find((x) => x.key === "evac");
    expect(evac).toMatchObject({ after: "35 still inside", worse: true });
  });

  it("flags nothing when nothing got worse", () => {
    const same = estimate(1200, 200, 2, 2000, 78);
    expect(whatIfRows({ ...same, before: same, params: PARAMS }).some((x) => x.worse)).toBe(false);
  });
});

describe("whatIfChips and cappedNote", () => {
  it("names each change in plain words", () => {
    expect(whatIfChips(PARAMS)).toEqual(["Crowd 200%", "Rain: walking at 85% speed", "South door 1 closed"]);
    expect(whatIfChips({ ...PARAMS, crowd_scale: 1, weather: "smoke", speed_factor: 0.6, closed_exits: [] }))
      .toEqual(["Smoke or dark: walking at 60% speed"]);
  });

  it("explains a capped crowd size", () => {
    expect(cappedNote(PARAMS)).toBeNull();
    expect(cappedNote({ ...PARAMS, crowd_scale: 3, crowd_scale_asked: 10, capped: true }))
      .toBe("You asked for 10×; the most I try is 3×");
  });
});

describe("askError", () => {
  it("explains an unreachable AI by what was asked", () => {
    const down = (intent: string) => new ApiError(503, "llm_unavailable", "x", null, { intent, routed_by: "keywords" });
    expect(askError(down("edit")).text).toMatch(/can't change the venue/);
    expect(askError(down("question")).text).toMatch(/can't answer questions/);
    expect(askError(down("edit")).intent).toBe("edit");
  });

  it("offers the exits that exist when a name is unknown", () => {
    const e = new ApiError(422, "unknown_exit", "There is no exit called “VIP gate” in this venue.", "Exits here: A, B.",
                           { unknown: ["VIP gate"], valid: ["South door 1", "South door 2"], intent: "what_if" });
    expect(askError(e)).toMatchObject({ exits: ["South door 1", "South door 2"], unknown: ["VIP gate"], intent: "what_if" });
  });

  it("passes other errors through", () => {
    expect(askError(new Error("boom"))).toMatchObject({ text: "boom", intent: null, exits: [] });
  });
});

describe("retryWithExit", () => {
  it("swaps the unknown name for a real exit, whatever its case", () => {
    expect(retryWithExit("close the VIP gate and it rains", ["vip gate"], "South door 1")).toBe("close the South door 1 and it rains");
  });

  it("asks a plain what-if when the name is not in the text", () => {
    expect(retryWithExit("shut the back", ["rear exit"], "South door 2")).toBe("what if South door 2 is closed?");
  });
});
