/** Reader for density.bin: uint8 [frames, floors, ny, nx], value × scale = people per m². */

/** Top of every density scale (heatmap, legend, peak chart), in people per m²: above the
 * danger line with room to spare, so one scale reads the same everywhere. */
export const DENSITY_MAX = 7;

export interface DensityIndex {
  format: string;
  times: number[];
  origin: [number, number];
  cell_m: number;
  nx: number;
  ny: number;
  floors: string[];
  scale: number;
  shape: number[];
  warn: number;
  danger: number;
  peak_series: number[];
  peak_map: number[][][];
}

export class DensityGrid {
  readonly index: DensityIndex;
  readonly data: Uint8Array;
  readonly frameSize: number;
  /** top of the colour scale; unset = people per m² ({@link DENSITY_MAX}). Grids in
   * another unit (crowd pressure) set their own. */
  displayMax?: number;

  constructor(index: DensityIndex, buf: ArrayBuffer, displayMax?: number) {
    this.index = index;
    this.displayMax = displayMax;
    this.data = new Uint8Array(buf);
    this.frameSize = index.nx * index.ny;
  }

  get frameCount(): number {
    return this.index.times.length;
  }

  /** Stored frame pair around t and the blend factor. */
  pairAt(t: number): [number, number, number] {
    const times = this.index.times;
    if (!times.length) return [0, 0, 0];
    if (t <= times[0]) return [0, 0, 0];
    const last = times.length - 1;
    if (t >= times[last]) return [last, last, 0];
    let lo = 0;
    let hi = last;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (times[mid] <= t) lo = mid;
      else hi = mid - 1;
    }
    const f = (t - times[lo]) / (times[lo + 1] - times[lo] || 1);
    return [lo, lo + 1, f];
  }

  /** Subarray for (frame, floor), row-major [ny][nx]. */
  slice(frame: number, floor: number): Uint8Array {
    const floors = this.index.floors.length;
    const start = (frame * floors + floor) * this.frameSize;
    return this.data.subarray(start, start + this.frameSize);
  }

  /** Density (people per m²) at a venue point for a stored frame. */
  at(frame: number, floor: number, x: number, y: number): number {
    const ix = Math.floor((x - this.index.origin[0]) / this.index.cell_m);
    const iy = Math.floor((y - this.index.origin[1]) / this.index.cell_m);
    if (ix < 0 || iy < 0 || ix >= this.index.nx || iy >= this.index.ny) return 0;
    return this.slice(frame, floor)[iy * this.index.nx + ix] * this.index.scale;
  }
}
