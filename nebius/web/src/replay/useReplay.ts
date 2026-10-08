/** Load a run's trajectory and density grid as binary ArrayBuffers (never as large JSON). */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { DensityGrid, type DensityIndex } from "./density";
import { Trajectory, type TrajIndex } from "./trajectory";

export interface Replay {
  traj: Trajectory;
  density: DensityGrid | null;
}

export function useReplay(runId: string | null | undefined, enabled = true) {
  return useQuery({
    queryKey: ["replay", runId],
    enabled: !!runId && enabled,
    staleTime: Infinity,
    gcTime: 90_000, // keep at most a couple of runs in memory
    retry: false,
    queryFn: async ({ signal }): Promise<Replay> => {
      const [tIdx, tBuf] = await Promise.all([
        api.get<TrajIndex>(`/runs/${runId}/trajectory/index`, signal),
        api.binary(`/runs/${runId}/trajectory`, signal),
      ]);
      let density: DensityGrid | null = null;
      try {
        const [dIdx, dBuf] = await Promise.all([
          api.get<DensityIndex>(`/runs/${runId}/density/index`, signal),
          api.binary(`/runs/${runId}/density`, signal),
        ]);
        density = new DensityGrid(dIdx, dBuf);
      } catch {
        density = null;
      }
      return { traj: new Trajectory(tIdx, tBuf), density };
    },
  });
}
