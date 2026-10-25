/** The red team's failure map in Your plan › Scenarios: every way the plan broke, one cell per
 * kind of hazard and place (a quality-diversity archive, docs/RAINBOW.md). Hidden for sessions
 * from before the map existed (a finished session whose summary has no archive is not asked;
 * the archive endpoint answers 404 for them). Picking an attack plays its
 * simulation in the Replay tab. */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { FailureMap } from "@/panels/FailureMap";
import type { FailureMap as FailureMapData } from "@/panels/failureMap";

export function FailureMapSlot({ sessionId, hasArchive = true, onSelectRun }: {
  projectId: string; sessionId: string | null; hasArchive?: boolean; onSelectRun: (runId: string, title: string) => void;
}) {
  const archive = useQuery({
    queryKey: ["session", sessionId, "archive"],
    enabled: !!sessionId && hasArchive,
    retry: false,
    staleTime: 60_000,
    queryFn: ({ signal }) => api.get<FailureMapData>(`/sessions/${sessionId}/archive`, signal),
  });
  const map = archive.data;
  if (!sessionId || !map || !map.cells?.length) return null;
  const titleOf = (runId: string) => {
    for (const c of map.cells) for (const e of c.elites) if (e.run_id === runId || e.after_run_id === runId) return e.title;
    return "";
  };
  return <FailureMap map={map} onSelectRun={(runId) => onSelectRun(runId, titleOf(runId))} />;
}
