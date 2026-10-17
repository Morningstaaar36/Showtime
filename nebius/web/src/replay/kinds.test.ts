import { describe, expect, it } from "vitest";
import { kindsPresent, parseAgentKinds, PEOPLE_KINDS } from "./kinds";
import { Trajectory, type TrajIndex } from "./trajectory";

describe("people kinds of a run", () => {
  it("reads the agents.json contract into a lookup by agent id", () => {
    const k = parseAgentKinds({ schema: 1, kinds: { "3": "bed", "7": "wheelchair", "8": "bed", "9": "staff" } })!;
    expect(PEOPLE_KINDS[k.lookup[3]]).toBe("bed");
    expect(PEOPLE_KINDS[k.lookup[7]]).toBe("wheelchair");
    expect(PEOPLE_KINDS[k.lookup[4]]).toBe("general");
    expect(k.listed).toMatchObject({ bed: 2, wheelchair: 1, staff: 1, child: 0 });
    expect(kindsPresent(k)).toEqual(["general", "wheelchair", "bed", "staff"]);
  });
  it("treats older runs, general-only runs and junk as no kinds", () => {
    expect(parseAgentKinds({ schema: 1, kinds: {} })).toBeNull();
    expect(parseAgentKinds({ schema: 1, kinds: { "1": "general" } })).toBeNull();
    expect(parseAgentKinds({ schema: 1, kinds: { x: "bed", "70000": "bed", "2": "dragon" } })).toBeNull();
    expect(parseAgentKinds(null)).toBeNull();
    expect(parseAgentKinds("nope")).toBeNull();
    expect(kindsPresent(null)).toEqual([]);
  });
});

/** traj.bin with `frames` frames of `n` people walking east (layout of sim/metrics.py). */
function syntheticTrajectory(n: number, frames: number): Trajectory {
  const frameBytes = 4 + n * 2 * 3 + n;
  const padded = frameBytes + ((4 - (frameBytes % 4)) % 4);
  const buf = new ArrayBuffer(padded * frames);
  const offsets: number[] = [];
  for (let f = 0; f < frames; f++) {
    const off = f * padded;
    offsets.push(off);
    new DataView(buf).setUint32(off, n, true);
    const ids = new Uint16Array(buf, off + 4, n);
    const xs = new Int16Array(buf, off + 4 + 2 * n, n);
    const ys = new Int16Array(buf, off + 4 + 4 * n, n);
    for (let i = 0; i < n; i++) { ids[i] = i; xs[i] = (i % 100) * 10 + f; ys[i] = Math.floor(i / 100) * 10; }
  }
  const index: TrajIndex = { format: "v1", times: offsets.map((_, f) => f * 0.25), offsets, bytes: buf.byteLength, origin: [0, 0],
    scale: 0.05, floors: ["F0"], bounds: [0, 0, 50, 50], max_agents: n };
  return new Trajectory(index, buf);
}

describe("replay frame loop with 3,000 people", () => {
  it("samples positions and agent ids well inside a 30 fps frame budget", () => {
    const n = 3000;
    const traj = syntheticTrajectory(n, 40);
    const kinds = parseAgentKinds({ schema: 1, kinds: Object.fromEntries(Array.from({ length: n / 3 }, (_, i) => [String(i * 3), "bed"])) })!;
    const out = new Float32Array(n * 3);
    const ids = new Uint16Array(n);
    const perKind = new Int32Array(PEOPLE_KINDS.length);
    const frames = 300;
    const t0 = performance.now();
    for (let k = 0; k < frames; k++) {
      const m = traj.sample((k % 39) * 0.25 + 0.1, out, ids);
      perKind.fill(0);
      for (let j = 0; j < m; j++) perKind[kinds.lookup[ids[j]]]++;
    }
    const ms = (performance.now() - t0) / frames;
    expect(perKind[PEOPLE_KINDS.indexOf("bed")]).toBe(1000);
    expect(ids[5]).toBe(5);
    // the JS side of a frame must leave most of the 33 ms for rendering
    expect(ms).toBeLessThan(8);
  });
});
