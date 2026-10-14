import { describe, expect, it } from "vitest";
import type { CostRecord } from "@/lib/evidence";
import { costView } from "./cost";

const bucket = (calls: number, usd = 0) => ({ calls, tokens_in: calls * 1000, tokens_out: calls * 200, usd });
const record = (over: Partial<CostRecord> = {}): CostRecord => ({
  usd_total: 0, tokens_in: 12_000, tokens_out: 2_400, calls: 12, llm_cache_hits: 0,
  by_role: { red_team: bucket(4), blue_team: bucket(8) },
  by_model: { "nvidia/nemotron-nano-9b-v2:free": bucket(12) },
  sims: { instant_estimates: 9, quick_sims: 6, full_sims: 1, failed: 0, cache_hits: 0, sim_seconds: 72.4 },
  wall_s: 184.2,
  ...over,
});

describe("How this plan was made", () => {
  it("shows free and local models as $0.00", () => {
    const v = costView(record());
    expect(v?.total).toBe("$0.00");
    expect(v?.free).toBe(true);
  });

  it("shows a paid model's cost, its calls and tokens", () => {
    const v = costView(record({ usd_total: 0.0123, llm_cache_hits: 3,
      by_model: { "meta/llama": bucket(10, 0.0123), local: bucket(2) } }));
    expect(v?.total).toBe("$0.01");
    expect(v?.free).toBe(false);
    expect(v?.calls).toBe("12 (12.0k tokens in, 2.4k out) · 3 answered from the cache");
    expect(v?.models).toEqual([
      { name: "meta/llama", detail: "10 calls · 12.0k tokens · $0.01" },
      { name: "local", detail: "2 calls · 2.4k tokens · $0.00" },
    ]);
  });

  it("counts simulations by kind, with the ones that didn't finish or were reused", () => {
    const v = costView(record());
    expect(v?.sims).toBe("1 full simulation · 6 quick simulations · 9 instant estimates");
    expect(v?.simsNote).toBe("");
    const w = costView(record({ sims: { instant_estimates: 1, quick_sims: 0, full_sims: 2, failed: 1, cache_hits: 2, sim_seconds: 0 } }));
    expect(w?.sims).toBe("2 full simulations · 1 instant estimate");
    expect(w?.simsNote).toBe("1 didn't finish · 2 reused");
  });

  it("formats compute and wall time", () => {
    const v = costView(record());
    expect(v?.compute).toBe("1 min 12 s");
    expect(v?.wall).toBe("3 min 4 s");
  });

  it("has nothing to show for sessions saved before the record existed", () => {
    expect(costView(null)).toBeNull();
    expect(costView(record({ sims: { instant_estimates: 0, quick_sims: 0, full_sims: 0, failed: 0, cache_hits: 0, sim_seconds: 0 } }))?.sims).toBe("None");
  });
});
