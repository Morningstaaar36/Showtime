import { describe, expect, it } from "vitest";
import type { Attack } from "@/api/types";
import { evidenceGroups } from "./evidence";

const atk = (id: string, title: string, src: Record<string, unknown>) =>
  ({ attack_id: id, title, events: [], inspired_by: src }) as unknown as Attack;

describe("the test's evidence, by origin", () => {
  it("lists each source once with the attacks it grounds, web and dataset apart", () => {
    const g = evidenceGroups([
      atk("A1", "Gate C jams", { incident: "Stadium gate crush", year: 2023, source_url: "https://e.org/a", evidence: "Gate C opened late.", origin: "tavily" }),
      atk("A2", "Late surge", { incident: "Stadium gate crush", year: 2023, source_url: "https://e.org/a", evidence: "Gate C opened late.", origin: "tavily" }),
      atk("A3", "Door blocked", { incident: "Nightclub fire", year: 2003, source_url: "https://en.wikipedia.org/wiki/x", evidence: "One exit.", dataset_row: 7 }),
    ]);
    expect(g.tavily).toEqual([{ url: "https://e.org/a", title: "Stadium gate crush", year: 2023, sentence: "Gate C opened late.", origin: "tavily", attacks: ["Gate C jams", "Late surge"] }]);
    expect(g.dataset.map((e) => [e.title, e.origin, e.attacks])).toEqual([["Nightclub fire", "dataset", ["Door blocked"]]]);
  });
  it("treats a source saved before origins existed as the dataset", () => {
    const g = evidenceGroups([atk("A1", "x", { incident: "Old", source_url: "https://e.org/o" })]);
    expect(g.dataset).toHaveLength(1);
    expect(g.tavily).toHaveLength(0);
  });
});
