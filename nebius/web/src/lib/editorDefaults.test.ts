import { describe, expect, it } from "vitest";
import { editorDefaultsOf } from "./editorDefaults";

describe("editor defaults", () => {
  it("reads the server's editor table and crowd cap", () => {
    const ed = editorDefaultsOf({ max_people: 3000, editor: { exit_width_m: 2.4, zone_density_ppm2: 1.5, min_width_m: 0.8 } });
    expect(ed).toMatchObject({ exitWidth: 2.4, zoneDensity: 1.5, minWidth: 0.8, maxPeople: 3000 });
  });
  it("uses the documented fallback for anything missing", () => {
    expect(editorDefaultsOf({ editor: { door_width_m: "wide" } })).toEqual(editorDefaultsOf({}));
    expect(editorDefaultsOf({}).doorWidth).toBe(1);
  });
});
