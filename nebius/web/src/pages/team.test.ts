import { describe, expect, it } from "vitest";
import { modelName } from "./Team";

describe("AI team", () => {
  it("names Nemotron models for people", () => {
    expect(modelName("nvidia/nemotron-3.5-lightning:free")).toBe("Nemotron 3.5 Lightning");
    expect(modelName("nvidia/nemotron-3-ultra-550b-a55b:free")).toBe("Nemotron 3 Ultra");
    expect(modelName("nemotron-nano-9b-v2-q4_k_m")).toBe("Nemotron Nano 9b V2 Q4_k_m");
  });
});
