/** Your plan › Floors: per storey, how many people start there, how that falls over time and when
 * the floor is clear, and how many people took each stair (from the trajectory: a person whose
 * floor changes between two frames used the stair joining those floors nearest to where they
 * arrived). Pure. */
import type { Pt, Stair, Venue } from "@/api/types";
import { centroid } from "@/scene/geom";

interface FloorStat {
  floorId: string;
  start: number;
  /** people on the floor over time (about `points` samples) */
  series: number[];
  /** seconds until nobody is left on the floor for good (null: never cleared in the replay) */
  clearS: number | null;
}

interface FloorsSummary {
  floors: FloorStat[];
  /** people who walked each stair (either way) */
  stairs: Record<string, number>;
}

/** The part of a trajectory this needs (Trajectory satisfies it). */
export interface TrajLike {
  index: { times: number[]; floors: string[]; origin: [number, number]; scale: number };
  frameCount: number;
  frame(k: number): { n: number; ids: Uint16Array; xs: Int16Array; ys: Int16Array; floors: Uint8Array };
}

/** `allOutS`: when the run reports everyone out, the time the last person left. The final
 * trajectory frame can still hold people stepping through an exit at that instant; their floor
 * is clear then, not "never". */
export function floorsSummary(traj: TrajLike, venue: Venue, points = 120, allOutS: number | null = null): FloorsSummary {
  const fl = traj.index.floors;
  const total = traj.frameCount;
  const [ox, oy] = traj.index.origin;
  const sc = traj.index.scale;
  const step = Math.max(1, Math.floor(total / Math.max(points, 1)));
  const series: number[][] = fl.map(() => []);
  const clear: (number | null)[] = fl.map(() => null);
  const start: number[] = fl.map(() => 0);
  const stairs: Record<string, number> = {};
  const byPair = new Map<string, { s: Stair; at: Record<string, [number, number]> }[]>();
  for (const s of venue.stairs ?? []) {
    const key = [s.from_floor, s.to_floor].sort().join("|");
    const at = { [s.from_floor]: centroid(s.top_polygon as Pt[]), [s.to_floor]: centroid(s.bottom_polygon as Pt[]) };
    byPair.set(key, [...(byPair.get(key) ?? []), { s, at }]);
    stairs[s.id] = 0;
  }
  const last = new Map<number, number>();
  for (let k = 0; k < total; k++) {
    const f = traj.frame(k);
    const counts = fl.map(() => 0);
    for (let i = 0; i < f.n; i++) {
      const fi = f.floors[i];
      if (fi < counts.length) counts[fi] += 1;
      const id = f.ids[i];
      const prev = last.get(id);
      if (prev !== undefined && prev !== fi && fl[prev] && fl[fi]) {
        const options = byPair.get([fl[prev], fl[fi]].sort().join("|"));
        if (options?.length) {
          const x = ox + f.xs[i] * sc, y = oy + f.ys[i] * sc;
          let best = options[0], d = Infinity;
          for (const o of options) {
            const p = o.at[fl[fi]];
            const dd = p ? Math.hypot(p[0] - x, p[1] - y) : Infinity;
            if (dd < d) { d = dd; best = o; }
          }
          stairs[best.s.id] += 1;
        }
      }
      last.set(id, fi);
    }
    if (k === 0) counts.forEach((c, j) => { start[j] = c; });
    counts.forEach((c, j) => {
      // clear when it is finally empty: people coming down from above can fill it again
      if (c > 0) clear[j] = null;
      else if (clear[j] === null && start[j] > 0) clear[j] = traj.index.times[k];
    });
    if (k % step === 0 || k === total - 1) counts.forEach((c, j) => series[j].push(c));
  }
  if (allOutS != null) {
    fl.forEach((_, j) => {
      if (clear[j] === null && start[j] > 0) {
        clear[j] = Math.max(allOutS, traj.index.times[total - 1] ?? allOutS);
        series[j].push(0);
      }
    });
  }
  return { floors: fl.map((id, j) => ({ floorId: id, start: start[j], series: series[j], clearS: clear[j] })), stairs };
}
