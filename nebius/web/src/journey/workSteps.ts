/** Plain-language steps of "AI at work", derived from the session's phase history. */

export type StepKey = "simulate" | "attack" | "fix" | "confirm" | "write";
export type StepStatus = "pending" | "running" | "done" | "skipped" | "failed";

/** Session phases (orchestrator/session.py) grouped into the steps an organizer sees. */
export const WORK_STEPS: { key: StepKey; phases: string[] }[] = [
  { key: "simulate", phases: ["baseline"] },
  { key: "attack", phases: ["red_team", "screening", "simulating"] },
  { key: "fix", phases: ["blue_team"] },
  { key: "confirm", phases: ["confirming"] },
  { key: "write", phases: ["judging"] },
];

export interface WorkStep {
  key: StepKey;
  status: StepStatus;
  /** seconds spent in the step so far (null if never entered) */
  elapsedS: number | null;
}

export function workSteps(history: { phase: string; ts: string }[], opts: { ended: boolean; failed: boolean; now: number }): WorkStep[] {
  const current = history[history.length - 1]?.phase ?? "";
  const live = !opts.ended && current !== "done";
  const lastEntered = Math.max(-1, ...WORK_STEPS.map((s, i) => (history.some((h) => s.phases.includes(h.phase)) ? i : -1)));
  return WORK_STEPS.map((step, i) => {
    let elapsed = 0;
    let entered = false;
    history.forEach((h, j) => {
      if (!step.phases.includes(h.phase)) return;
      entered = true;
      const until = history[j + 1] ? Date.parse(history[j + 1].ts) : live ? opts.now : Date.parse(h.ts);
      elapsed += Math.max(0, (until - Date.parse(h.ts)) / 1000);
    });
    const isCurrent = step.phases.includes(current);
    let status: StepStatus;
    if (entered) status = isCurrent && opts.failed ? "failed" : isCurrent && live ? "running" : "done";
    else status = i < lastEntered || !live ? "skipped" : "pending";
    return { key: step.key, status, elapsedS: entered ? elapsed : null };
  });
}
