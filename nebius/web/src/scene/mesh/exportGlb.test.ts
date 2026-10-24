import { describe, expect, it } from "vitest";
import type { Floor, Pt, Stair, Venue } from "@/api/types";
import { glbFileName, venueGlb } from "./exportGlb";

const rect = (x0: number, y0: number, x1: number, y1: number): Pt[] => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];

const venue = {
  venue_id: "v", name: "City hospital · 2 floors", description: "", mode: "indoor", routes: [], stage: null,
  floors: [
    { floor_id: "F0", name: "Ground", elevation_m: 0, walkable: rect(0, 0, 30, 20), zones: [],
      obstacles: [{ id: "w1", kind: "wall", label: "Ward wall", polygon: rect(10, 5, 10.15, 20), height_m: null, line: null }],
      exits: [{ id: "front", polygon: rect(14, 0.02, 16, 0.42), width_m: 2, blocked: false, label: "Main entrance" }] },
    { floor_id: "F1", name: "1st floor", elevation_m: 3.5, walkable: rect(0, 0, 30, 20), zones: [], obstacles: [], exits: [] },
  ] as Floor[],
  stairs: [{ id: "s1", from_floor: "F1", to_floor: "F0", top_polygon: rect(1, 9, 3, 11), bottom_polygon: rect(5, 9, 7, 11), width_m: 1.2, length_m: 7 }] as Stair[],
} as unknown as Venue;

function parseGlb(buf: ArrayBuffer): { magic: string; version: number; json: { nodes: { name?: string; children?: number[] }[]; meshes: unknown[]; materials: { name?: string }[]; scenes: { nodes: number[] }[] } } {
  const dv = new DataView(buf);
  const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
  const version = dv.getUint32(4, true);
  expect(dv.getUint32(8, true)).toBe(buf.byteLength);
  const jsonLen = dv.getUint32(12, true);
  expect(dv.getUint32(16, true)).toBe(0x4e4f534a); // "JSON"
  const json = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 20, jsonLen)));
  return { magic, version, json };
}

describe("3D model export", () => {
  it("writes a binary glTF with a named node per floor and per object", async () => {
    const buf = await venueGlb(venue);
    const { magic, version, json } = parseGlb(buf);
    expect(magic).toBe("glTF");
    expect(version).toBe(2);
    const names = json.nodes.map((n) => n.name);
    expect(names).toContain("Ground");
    expect(names).toContain("1st floor");
    expect(names).toContain("Ward wall");
    expect(names).toContain("Exit · Main entrance");
    expect(names).toContain("Floor slab");
    expect(names.some((n) => n?.startsWith("Stair 1"))).toBe(true);
    // floors hold their objects
    const ground = json.nodes.find((n) => n.name === "Ground")!;
    expect(ground.children!.map((i) => json.nodes[i].name)).toContain("Ward wall");
    expect(json.materials.map((m) => m.name)).toEqual(expect.arrayContaining(["Floor", "Wall", "Exit", "Stair"]));
    expect(json.meshes.length).toBeGreaterThan(5);
  });

  it("names the file after the project", () => {
    expect(glbFileName("City hospital · 4 floors")).toBe("city-hospital-4-floors.glb");
    expect(glbFileName("  ")).toBe("venue.glb");
  });
});
