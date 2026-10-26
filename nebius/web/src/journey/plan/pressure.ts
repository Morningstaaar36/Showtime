/** Crowd pressure ("turbulence") of a run: GET /runs/{id}/pressure/index + /runs/{id}/pressure,
 * the same encoding as the density grid (uint8 frames × scale), read by {@link DensityGrid}.
 * A run simulated before pressure existed answers 404: that run has no layer (and no Turbulence
 * toggle); other runs still do. */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { DensityGrid, type DensityIndex } from "@/replay/density";

export interface PressureLayer {
  grid: DensityGrid;
  /** highest value in the run and when (from the index's peak series) */
  peak: number | null;
  peakAtS: number | null;
  warn: number;
  danger: number;
  /** top of the colour scale */
  max: number;
  unit: string | null;
}

/** Peak and colour range of a pressure index (thresholds come with the index). */
export function pressureRange(idx: DensityIndex & { unit?: string; max?: number }): Omit<PressureLayer, "grid"> {
  const series = idx.peak_series ?? [];
  let k = -1;
  series.forEach((v, i) => { if (k < 0 || v > series[k]) k = i; });
  const peak = k >= 0 ? series[k] : null;
  // values are stored as uint8 steps of `scale`, so nothing above 255 × scale can be shown
  const top = idx.scale ? 255 * idx.scale : Infinity;
  const max = Math.min(Math.max(idx.max ?? 0, idx.danger * 1.4, peak ?? 0, 1e-6), top);
  // the series has one value per simulation frame, thinned evenly; the stored frames are fewer
  // (one a second), so its index maps to the run's time by position, not to idx.times[k]
  const times = idx.times ?? [];
  const end = times.length ? times[times.length - 1] : null;
  const peakAtS = k >= 0 && end != null ? (series.length > 1 ? (k / (series.length - 1)) * end : 0) : null;
  const unit = idx.unit ? idx.unit.replace(/s2$/, "s²") : null; // the index writes "1/s2"
  return { peak, peakAtS, warn: idx.warn, danger: idx.danger, max, unit };
}

export function usePressure(runId: string | null | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["pressure", runId],
    enabled: !!runId && enabled,
    retry: false,
    staleTime: Infinity,
    gcTime: 90_000,
    queryFn: async ({ signal }): Promise<PressureLayer | null> => {
      try {
        // runs simulated before the pressure grid existed have none: ask the run first
        const run = await api.get<{ result?: { artifacts?: Record<string, string | null> } | null }>(`/runs/${runId}`, signal);
        if (!run.result?.artifacts?.pressure_grid) return null;
        const idx = await api.get<DensityIndex & { unit?: string; max?: number }>(`/runs/${runId}/pressure/index`, signal);
        const buf = await api.binary(`/runs/${runId}/pressure`, signal);
        const range = pressureRange(idx);
        return { grid: new DensityGrid(idx, buf, range.max), ...range };
      } catch {
        return null; // this run has no pressure grid (simulated before it existed)
      }
    },
  });
}
