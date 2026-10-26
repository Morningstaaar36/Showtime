import { describe, expect, it } from "vitest";
import { tileUrl, useMapConfig } from "./mapConfig";

describe("map config from the server", () => {
  it("fills a raster tile template", () => {
    expect(tileUrl("https://t.example/{z}/{x}/{y}.png", 15, 23_000, 14_000)).toBe("https://t.example/15/23000/14000.png");
  });
  it("is empty until the server sends it, then holds it", () => {
    expect(useMapConfig.getState().config).toBeNull();
    const cfg = { style_url: "s", raster_tiles_url: "r/{z}/{x}/{y}", start: { lat: 1, lon: 2, zoom: 3 } };
    useMapConfig.getState().set(cfg);
    expect(useMapConfig.getState().config).toEqual(cfg);
  });
});
