import { describe, expect, it } from "vitest";
import { analysisView, guessKind, showValue, starterScript } from "@/journey/analysis";

const OUTPUT = {
  facts: { "longest queue (people)": 37, minutes_with_a_queue: 4.5 },
  table: [{ minute: 1, people: 12 }, { minute: 2, people: 37 }, { minute: 3, people: null }],
  chart: { x: "minute", y: "people", title: "Queue at Gate B" },
};

describe("analysisView", () => {
  it("shows the facts, the table and a bar per numeric row, values as the code printed them", () => {
    const v = analysisView(OUTPUT);
    expect(v.facts).toEqual([
      { label: "longest queue (people)", value: "37" },
      { label: "minutes with a queue", value: "4.5" },
    ]);
    expect(v.table).toEqual({ columns: ["minute", "people"], rows: [["1", "12"], ["2", "37"], ["3", "–"]] });
    expect(v.chart?.title).toBe("Queue at Gate B");
    expect(v.chart?.bars.map((b) => [b.label, b.value])).toEqual([["1", 12], ["2", 37]]);
    expect(v.chart?.max).toBe(37);
  });

  it("reads flat outputs, plain values and lists of rows", () => {
    expect(analysisView({ peak: 3.14159, worst_minute: 7 }).facts).toEqual([
      { label: "peak", value: "3.14" }, { label: "worst minute", value: "7" },
    ]);
    expect(analysisView(42).facts).toEqual([{ label: "Result", value: "42" }]);
    expect(analysisView([{ a: 1 }]).table?.rows).toEqual([["1"]]);
    expect(analysisView(null)).toEqual({ facts: [], table: null, chart: null, raw: "null" });
  });

  it("ignores a chart that names no numeric column and caps the rows", () => {
    expect(analysisView({ table: [{ a: "x" }], chart: { x: "a", y: "b" } }).chart).toBeNull();
    const rows = Array.from({ length: 50 }, (_, i) => ({ i }));
    expect(analysisView({ table: rows }).table?.rows).toHaveLength(30);
  });
});

describe("script helpers", () => {
  it("formats values without inventing precision", () => {
    expect([showValue(1234.5), showValue(true), showValue("Gate B"), showValue(undefined)]).toEqual(["1,234.5", "yes", "Gate B", "–"]);
  });

  it("guesses the kind and starts from a working script", () => {
    expect(guessKind("def on_step(view, act):\n    pass")).toBe("scenario");
    expect(guessKind("import showtime_data as sd\noutput = 1")).toBe("analysis");
    expect(starterScript("scenario", "door_s1")).toContain('act.close_exit("door_s1")');
    expect(starterScript("analysis", null)).toContain("output = {");
  });
});
