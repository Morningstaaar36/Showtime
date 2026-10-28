import { describe, expect, it } from "vitest";
import { speedPresetsOf } from "./speedPresets";

describe("speed presets", () => {
  it("takes the server's table in its order", () => {
    expect(speedPresetsOf({ speed_presets: { normal: 1, smoke: 0.5, dark: 0.7 } }))
      .toEqual([{ key: "normal", factor: 1 }, { key: "smoke", factor: 0.5 }, { key: "dark", factor: 0.7 }]);
  });
  it("falls back to the built-in table until the settings arrive", () => {
    expect(speedPresetsOf({}).map((p) => p.key)).toEqual(["normal", "rain", "families", "smoke"]);
    expect(speedPresetsOf({ speed_presets: { broken: "x" } })).toHaveLength(4);
  });
});
