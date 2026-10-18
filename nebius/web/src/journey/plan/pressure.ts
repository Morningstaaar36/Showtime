/** Crowd pressure ("turbulence") of a run, from GET /runs/{id}/pressure when the server has it.
 * Until then the layer stays hidden: a 404 marks the route missing for this page load, so the
 * replay never asks again. The shape is read loosely (peak value and when) so the toggle works
 * with the first version of the endpoint; the 3D layer plugs in here once the format is fixed. */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

let missing = false;

export interface PressureSummary {
  /** highest pressure in the run, in the endpoint's unit */
  peak: number | null;
  /** when it peaks (s) */
  peakAtS: number | null;
  unit: string | null;
  raw: Record<string, unknown>;
}

const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);

export function readPressure(raw: Record<string, unknown>): PressureSummary {
  return {
    peak: num(raw.peak) ?? num(raw.peak_pressure) ?? num(raw.max),
    peakAtS: num(raw.peak_at_s) ?? num(raw.peak_t_s) ?? num(raw.t_peak_s),
    unit: typeof raw.unit === "string" ? raw.unit : null,
    raw,
  };
}

export function usePressure(runId: string | null | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["pressure", runId],
    enabled: !!runId && enabled && !missing,
    retry: false,
    staleTime: Infinity,
    queryFn: async ({ signal }): Promise<PressureSummary | null> => {
      try {
        return readPressure(await api.get<Record<string, unknown>>(`/runs/${runId}/pressure`, signal));
      } catch (e) {
        if ((e as { status?: number }).status === 404) missing = true;
        return null;
      }
    },
  });
}
