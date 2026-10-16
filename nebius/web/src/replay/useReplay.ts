/** Load a run's trajectory and density grid as binary ArrayBuffers (never as large JSON). */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { DensityGrid, type DensityIndex } from "./density";
import { type AgentKinds, parseAgentKinds } from "./kinds";
import { Trajectory, type TrajIndex } from "./trajectory";

export interface Replay {
  traj: Trajectory;
  density: DensityGrid | null;
  /** who each person is (G2-04); null for older runs and runs of general adults only */
  kinds: AgentKinds | null;
}

/** A server without GET /runs/{id}/agents (before G2-04) answers 404: ask once per page load, not
 * once per run, so the console stays clean. */
let agentsUnsupported = false;

async function agentKinds(runId: string, signal: AbortSignal): Promise<AgentKinds | null> {
  if (agentsUnsupported) return null;
  try {
    return parseAgentKinds(await api.get<unknown>(`/runs/${runId}/agents`, signal));
  } catch (e) {
    // the run itself exists (its trajectory just loaded), so a 404 means the route is missing
    if ((e as { status?: number }).status === 404) agentsUnsupported = true;
    return null;
  }
}

export function useReplay(runId: string | null | undefined, enabled = true) {
  return useQuery({
    queryKey: ["replay", runId],
    enabled: !!runId && enabled,
    staleTime: Infinity,
    gcTime: 90_000, // keep at most a couple of runs in memory
    retry: false,
    queryFn: async ({ signal }): Promise<Replay> => {
      const [tIdx, tBuf, kinds] = await Promise.all([
        api.get<TrajIndex>(`/runs/${runId}/trajectory/index`, signal),
        api.binary(`/runs/${runId}/trajectory`, signal),
        // an older server has no /agents: everyone is drawn as a general adult
        agentKinds(runId!, signal),
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
      return { traj: new Trajectory(tIdx, tBuf), density, kinds };
    },
  });
}
