/** Follows an Autopilot run's SSE stream and folds it into view state (same pattern as
 * useSessionStream): reconnects from the last event it saw with ?after=. */
import { useEffect, useReducer, useRef } from "react";
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
    let es: EventSource | null = null;
    let closed = false;
    let retry: number | undefined;
    const open = () => {
      es = new EventSource(`/api/v1/autopilot/${runId}/events?after=${lastSeq.current}`);
      es.onopen = () => dispatch({ kind: "conn", v: true });
      es.onmessage = (m) => {
        try {
          dispatch({ kind: "event", ev: JSON.parse(m.data) as AutopilotEvent });
        } catch {
          /* ignore malformed lines */
        }
      };
      es.addEventListener("end", () => {
        closed = true;
        es?.close();
        dispatch({ kind: "end" });
      });
      es.onerror = () => {
        es?.close();
        dispatch({ kind: "conn", v: false });
        if (!closed) retry = window.setTimeout(open, 2000);
      };
    };
    open();
    return () => {
      closed = true;
      if (retry) window.clearTimeout(retry);
      es?.close();
    };
  }, [runId]);
  return state;
}
