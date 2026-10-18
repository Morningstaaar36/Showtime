/** Crowd pressure ("turbulence") of a run: GET /runs/{id}/pressure/index + /runs/{id}/pressure,
 * the same encoding as the density grid (uint8 frames × scale), read by {@link DensityGrid}.
 * Servers without it answer 404: the route is then marked missing for this page load and the
 * Turbulence toggle stays hidden. */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { DensityGrid, type DensityIndex } from "@/replay/density";

let missing = false;

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
  const max = Math.max(idx.max ?? 0, idx.danger * 1.4, peak ?? 0, 1e-6);
  return { peak, peakAtS: k >= 0 ? idx.times[k] ?? null : null, warn: idx.warn, danger: idx.danger, max, unit: idx.unit ?? null };
}

export function usePressure(runId: string | null | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["pressure", runId],
    enabled: !!runId && enabled && !missing,
    retry: false,
    staleTime: Infinity,
    gcTime: 90_000,
    queryFn: async ({ signal }): Promise<PressureLayer | null> => {
      try {
        const idx = await api.get<DensityIndex & { unit?: string; max?: number }>(`/runs/${runId}/pressure/index`, signal);
        const buf = await api.binary(`/runs/${runId}/pressure`, signal);
        const range = pressureRange(idx);
        return { grid: new DensityGrid(idx, buf, range.max), ...range };
      } catch (e) {
        if ((e as { status?: number }).status === 404) missing = true;
        return null;
      }
    },
  });
}
