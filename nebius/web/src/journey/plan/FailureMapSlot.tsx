/** Where the red team's failure map (web/src/panels/FailureMap.tsx: the archive of every way the
 * plan broke) sits in Your plan › Scenarios. Renders nothing until it is wired in: import
 * FailureMap here, load its archive, and render it (hidden when the archive endpoint 404s), with
 * `onSelectRun` playing the chosen run in the Replay tab. */
export function FailureMapSlot(_props: { projectId: string; sessionId: string | null; onSelectRun: (runId: string, title: string) => void }) {
  return null;
}
