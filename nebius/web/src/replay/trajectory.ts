/** Zero-copy reader for traj.bin (layout written by sim/metrics.py:write_trajectory).

Per frame: [u32 count][u16 ids × n][i16 x × n][i16 y × n][u8 floor × n][pad to 4 bytes].
Positions are int16 steps of `scale` metres from `origin`.
*/

export interface TrajIndex {
  format: string;
  times: number[];
  offsets: number[];
  bytes: number;
  origin: [number, number];
  scale: number;
  floors: string[];
  bounds: [number, number, number, number];
  max_agents: number;
}

export interface Frame {
  n: number;
  ids: Uint16Array;
  xs: Int16Array;
  ys: Int16Array;
  floors: Uint8Array;
}

export class Trajectory {
  readonly index: TrajIndex;
  private readonly buf: ArrayBuffer;
  private readonly view: DataView;
  private readonly cache = new Map<number, Frame>();
  /** Scratch lookup id -> slot in the "next" frame (ids are uint16). */
  private readonly slot = new Int32Array(65536).fill(-1);

  constructor(index: TrajIndex, buf: ArrayBuffer) {
    this.index = index;
    this.buf = buf;
    this.view = new DataView(buf);
  }

  get frameCount(): number {
    return this.index.times.length;
  }

  get duration(): number {
    const t = this.index.times;
    return t.length ? t[t.length - 1] : 0;
  }

  /** Largest frame index with time <= t. */
  frameAt(t: number): number {
    const times = this.index.times;
    let lo = 0;
    let hi = times.length - 1;
    if (hi < 0) return 0;
    if (t <= times[0]) return 0;
    if (t >= times[hi]) return hi;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (times[mid] <= t) lo = mid;
      else hi = mid - 1;
    }
    return lo;
  }

  frame(k: number): Frame {
    const hit = this.cache.get(k);
    if (hit) return hit;
    const off = this.index.offsets[k];
    const n = this.view.getUint32(off, true);
    const f: Frame = {
      n,
      ids: new Uint16Array(this.buf, off + 4, n),
      xs: new Int16Array(this.buf, off + 4 + 2 * n, n),
      ys: new Int16Array(this.buf, off + 4 + 4 * n, n),
      floors: new Uint8Array(this.buf, off + 4 + 6 * n, n),
    };
    if (this.cache.size > 8) this.cache.delete(this.cache.keys().next().value as number);
    this.cache.set(k, f);
    return f;
  }

  countAt(k: number): number {
    return this.view.getUint32(this.index.offsets[k], true);
  }

  /** People still inside per frame (for the evacuation curve). */
  counts(): number[] {
    return this.index.offsets.map((o) => this.view.getUint32(o, true));
  }

  /**
   * Interpolated positions at time t written into `out` as [x, y, floorIndex] triples (venue metres).
   * Returns the number of people. `ids`, when given, receives each person's agent id.
   */
  sample(t: number, out: Float32Array, ids?: Uint16Array): number {
    const k = this.frameAt(t);
    const a = this.frame(k);
    const times = this.index.times;
    const hasNext = k + 1 < times.length;
    const b = hasNext ? this.frame(k + 1) : null;
    const f = hasNext ? Math.min(1, Math.max(0, (t - times[k]) / (times[k + 1] - times[k] || 1))) : 0;
    const [ox, oy] = this.index.origin;
    const sc = this.index.scale;
    if (b) for (let j = 0; j < b.n; j++) this.slot[b.ids[j]] = j;
    const n = Math.min(a.n, out.length / 3);
    for (let i = 0; i < n; i++) {
      let x = a.xs[i];
      let y = a.ys[i];
      if (b) {
        const j = this.slot[a.ids[i]];
        if (j >= 0 && b.floors[j] === a.floors[i]) {
          x = x + (b.xs[j] - x) * f;
          y = y + (b.ys[j] - y) * f;
        }
      }
      out[i * 3] = ox + x * sc;
      out[i * 3 + 1] = oy + y * sc;
      out[i * 3 + 2] = a.floors[i];
      if (ids) ids[i] = a.ids[i];
    }
    if (b) for (let j = 0; j < b.n; j++) this.slot[b.ids[j]] = -1;
    return n;
  }
}
