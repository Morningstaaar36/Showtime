import { describe, expect, it } from "vitest";
import { Trajectory, type TrajIndex } from "./trajectory";

/** Encode frames in the traj.bin layout written by sim/metrics.py. */
function encode(frames: { id: number; x: number; y: number; floor: number }[][]): { buf: ArrayBuffer; offsets: number[] } {
  const sizes = frames.map((f) => { const raw = 4 + 7 * f.length; return raw + ((4 - (raw % 4)) % 4); });
  const buf = new ArrayBuffer(sizes.reduce((a, b) => a + b, 0));
  const view = new DataView(buf);
  const offsets: number[] = [];
  let off = 0;
  frames.forEach((f, k) => {
    offsets.push(off);
    const n = f.length;
    view.setUint32(off, n, true);
    f.forEach((p, i) => {
      view.setUint16(off + 4 + 2 * i, p.id, true);
      view.setInt16(off + 4 + 2 * n + 2 * i, p.x, true);
      view.setInt16(off + 4 + 4 * n + 2 * i, p.y, true);
      view.setUint8(off + 4 + 6 * n + i, p.floor);
    });
    off += sizes[k];
  });
  return { buf, offsets };
}

function make(): Trajectory {
  const { buf, offsets } = encode([
    [{ id: 1, x: 0, y: 0, floor: 0 }, { id: 2, x: 100, y: 100, floor: 0 }],
    [{ id: 2, x: 200, y: 100, floor: 0 }, { id: 1, x: 50, y: 0, floor: 0 }],
    [{ id: 2, x: 300, y: 100, floor: 0 }],
  ]);
  const index: TrajIndex = { format: "traj.bin/v1", times: [0, 0.25, 0.5], offsets, bytes: buf.byteLength,
    origin: [10, 20], scale: 0.02, floors: ["F0"], bounds: [0, 0, 40, 25], max_agents: 2 };
  return new Trajectory(index, buf);
}

describe("Trajectory", () => {
  it("reads counts per frame (people still inside)", () => {
    const t = make();
    expect(t.frameCount).toBe(3);
    expect(t.duration).toBe(0.5);
    expect(t.counts()).toEqual([2, 2, 1]);
  });

  it("finds the frame at or before a time", () => {
    const t = make();
    expect(t.frameAt(-1)).toBe(0);
    expect(t.frameAt(0.3)).toBe(1);
    expect(t.frameAt(9)).toBe(2);
  });

  it("interpolates by person id even when the order changes between frames", () => {
    const t = make();
    const out = new Float32Array(6);
    const n = t.sample(0.125, out);
    expect(n).toBe(2);
    // person 1: x 0 -> 50 steps, halfway = 25 steps = 0.5 m from origin x 10
    expect(out[0]).toBeCloseTo(10.5, 5);
    expect(out[1]).toBeCloseTo(20, 5);
    // person 2: x 100 -> 200 steps, halfway = 150 steps = 3 m
    expect(out[3]).toBeCloseTo(13, 5);
    expect(out[4]).toBeCloseTo(22, 5);
  });
});
