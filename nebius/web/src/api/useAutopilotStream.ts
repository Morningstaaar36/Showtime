/** Follows an Autopilot run's SSE stream and folds it into view state (same pattern as
 * useSessionStream): reconnects from the last event it saw with ?after=. */
import { useEffect, useReducer, useRef } from "react";
import { followStream } from "@/api/reconnect";
import { EMPTY_STREAM, foldAutopilot, type AutopilotStream } from "@/journey/autopilotSteps";
import type { AutopilotEvent } from "@/types/generated";

export function useAutopilotStream(runId: string | null | undefined): AutopilotStream {
  const [state, dispatch] = useReducer(foldAutopilot, EMPTY_STREAM);
  const lastSeq = useRef(0);
  lastSeq.current = state.lastSeq;

  useEffect(() => {
    dispatch({ kind: "reset" });
    lastSeq.current = 0;
    if (!runId) return;
    return followStream<AutopilotEvent>(() => `/api/v1/autopilot/${runId}/events?after=${lastSeq.current}`, {
      event: (ev) => dispatch({ kind: "event", ev }),
      conn: (v) => dispatch({ kind: "conn", v }),
      end: () => dispatch({ kind: "end" }),
    });
  }, [runId]);
  return state;
}
