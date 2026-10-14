/** Autopilot's eight plain-language steps (api/models/autopilot.py): folding its event stream,
 * the progress shown on "AI at work", and where the organizer goes when the plan is ready.
 * Pure functions, so they are unit tested. */
import type { AutopilotEvent, AutopilotRun, AutopilotStep } from "@/types/generated";

export type StepKey = AutopilotStep["key"];
export type RunStatus = AutopilotRun["status"];

export const STEP_KEYS: StepKey[] = ["understand", "venue", "capacity", "simulate", "attack", "fix", "confirm", "deliver"];

export interface AutopilotStream {
  lastSeq: number;
  steps: AutopilotStep[];
  projectId: string | null;
  projectName: string | null;
  sessionId: string | null;
  cost: { usd_total: number; tokens_total: number } | null;
  logs: { level: string; message: string }[];
  /** the run as it ended (the stream's last event) */
  final: AutopilotRun | null;
  connected: boolean;
  ended: boolean;
}

export const EMPTY_STREAM: AutopilotStream = {
  lastSeq: 0, steps: [], projectId: null, projectName: null, sessionId: null, cost: null, logs: [], final: null,
  connected: false, ended: false,
};

export type StreamAction = { kind: "event"; ev: AutopilotEvent } | { kind: "reset" } | { kind: "conn"; v: boolean } | { kind: "end" };

/** Fold one stream action into the view; events at or before the last seen one are ignored. */
export function foldAutopilot(s: AutopilotStream, a: StreamAction): AutopilotStream {
  if (a.kind === "reset") return EMPTY_STREAM;
  if (a.kind === "conn") return { ...s, connected: a.v };
  if (a.kind === "end") return { ...s, ended: true, connected: false };
  const ev = a.ev;
  if (ev.seq <= s.lastSeq) return s;
  const p = ev.payload as Record<string, unknown>;
  const next: AutopilotStream = { ...s, lastSeq: ev.seq };
  switch (ev.type) {
    case "step":
      next.steps = (p.steps as AutopilotStep[] | undefined) ?? s.steps;
      break;
    case "project":
      next.projectId = String(p.project_id);
      next.projectName = p.name ? String(p.name) : s.projectName;
      break;
    case "session":
      next.sessionId = String(p.session_id);
      break;
    case "cost":
      next.cost = { usd_total: Number(p.usd_total ?? 0), tokens_total: Number(p.tokens_total ?? 0) };
      break;
    case "log":
      next.logs = [...s.logs, { level: String(p.level ?? "info"), message: String(p.message ?? "") }].slice(-50);
      break;
    case "done": {
      const run = p as unknown as AutopilotRun;
      next.final = run;
      next.steps = run.steps ?? s.steps;
      next.projectId = run.project_id ?? s.projectId;
      next.projectName = run.project_name ?? s.projectName;
      next.sessionId = run.session_id ?? s.sessionId;
      break;
    }
    default:
      break;
  }
  return next;
}

export const isEnded = (status: RunStatus | undefined | null) => status === "finished" || status === "stopped" || status === "failed";

export interface AutopilotView {
  status: RunStatus | null;
  steps: AutopilotStep[];
  projectId: string | null;
  projectName: string | null;
  sessionId: string | null;
  usd: number | null;
  /** the ended run, from the stream or the API, whichever arrived first */
  final: AutopilotRun | null;
}

/** One view from the polled run and the live stream (the stream is fresher while it runs). */
export function autopilotView(run: AutopilotRun | undefined, stream: AutopilotStream): AutopilotView {
  const final = stream.final ?? (run && isEnded(run.status) ? run : null);
  const steps = final?.steps ?? (stream.steps.length ? stream.steps : run?.steps ?? []);
  return {
    status: final?.status ?? run?.status ?? null,
    steps,
    projectId: final?.project_id ?? stream.projectId ?? run?.project_id ?? null,
    projectName: final?.project_name ?? stream.projectName ?? run?.project_name ?? null,
    sessionId: final?.session_id ?? stream.sessionId ?? run?.session_id ?? null,
    usd: final?.cost?.usd_total ?? stream.cost?.usd_total ?? run?.cost?.usd_total ?? null,
    final,
  };
}

/** Seconds a step has taken so far (null before it starts). */
export function stepElapsed(step: AutopilotStep, now: number): number | null {
  if (!step.started_at) return null;
  const start = Date.parse(step.started_at);
  const end = step.finished_at ? Date.parse(step.finished_at) : step.status === "running" ? now : start;
  return Math.max(0, (end - start) / 1000);
}

export interface Progress {
  /** 0..100: finished steps, plus half of the running one */
  percent: number;
  current: AutopilotStep | null;
  /** the step to show as "Step n of N" */
  stepN: number;
  total: number;
}

export function autopilotProgress(steps: AutopilotStep[], ended: boolean): Progress {
  const total = steps.length || STEP_KEYS.length;
  const current = steps.find((s) => s.status === "running") ?? null;
  const finished = steps.filter((s) => s.status === "done" || s.status === "skipped" || s.status === "failed").length;
  const percent = ended ? 100 : Math.min(99, Math.round(((finished + (current ? 0.5 : 0)) / total) * 100));
  const stepN = current ? steps.indexOf(current) + 1 : Math.min(finished + 1, total);
  return { percent, current, stepN, total };
}

/** Your plan for an ended run: with its tested session when there is one. */
export function planHref(run: Pick<AutopilotRun, "project_id" | "session_id"> | null | undefined): string | null {
  if (!run?.project_id) return null;
  return run.session_id ? `/p/${run.project_id}?session=${run.session_id}` : `/p/${run.project_id}`;
}

/** Move on to Your plan by itself only when a tested plan exists (finished, or stopped after testing began). */
export function opensPlan(run: Pick<AutopilotRun, "status" | "project_id" | "session_id"> | null | undefined): boolean {
  return !!run && (run.status === "finished" || run.status === "stopped") && !!run.project_id && !!run.session_id;
}

/** The request that starts the same plan again. */
export function retryBody(run: Pick<AutopilotRun, "text" | "project_id" | "depth">): { text?: string; project_id?: string; depth: AutopilotRun["depth"] } {
  return run.text ? { text: run.text, depth: run.depth } : { project_id: run.project_id ?? undefined, depth: run.depth };
}
