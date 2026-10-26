import { describe, expect, it } from "vitest";
import {
  EMPTY_STREAM, STEP_KEYS, autopilotProgress, autopilotView, foldAutopilot, opensPlan, planHref, retryBody, stepElapsed,
  type AutopilotStream,
} from "@/journey/autopilotSteps";
import type { AutopilotEvent, AutopilotRun, AutopilotStep } from "@/types/generated";

const at = (s: number) => new Date(Date.UTC(2026, 9, 14, 10, 0, s)).toISOString();
const now = Date.parse(at(50));

function step(key: AutopilotStep["key"], status: AutopilotStep["status"], started: number | null = null, finished: number | null = null): AutopilotStep {
  return { key, label: key, status, started_at: started == null ? null : at(started), finished_at: finished == null ? null : at(finished), detail: null };
}
const pending = () => STEP_KEYS.map((k) => step(k, "pending"));
const ev = (seq: number, type: AutopilotEvent["type"], payload: Record<string, unknown>): AutopilotEvent => ({ seq, type, ts: at(seq), payload });
const fold = (events: AutopilotEvent[], from: AutopilotStream = EMPTY_STREAM) => events.reduce((s, e) => foldAutopilot(s, { kind: "event", ev: e }), from);

function run(over: Partial<AutopilotRun> = {}): AutopilotRun {
  return {
    id: "ap_1", status: "running", depth: "quick", text: "A concert for 400 people", project_id: null, project_name: null, session_id: null,
    steps: pending(), report_url: null, headline: null, cost: null, notes: [], evidence: [], ai_outage: false, partial_reason: null, error: null,
    created_at: at(0), finished_at: null, ...over,
  };
}

describe("foldAutopilot", () => {
  it("collects steps, the project, the session and the cost as they arrive", () => {
    const steps = [step("understand", "done", 0, 4), ...pending().slice(1)];
    const s = fold([
      ev(1, "step", { steps }),
      ev(2, "project", { project_id: "p_1", name: "Gym night" }),
      ev(3, "session", { session_id: "s_1" }),
      ev(4, "cost", { usd_total: 0.03, tokens_total: 1200 }),
      ev(5, "log", { level: "info", message: "Using a designed venue instead." }),
    ]);
    expect(s.lastSeq).toBe(5);
    expect(s.steps[0].status).toBe("done");
    expect([s.projectId, s.projectName, s.sessionId]).toEqual(["p_1", "Gym night", "s_1"]);
    expect(s.cost).toEqual({ usd_total: 0.03, tokens_total: 1200 });
    expect(s.logs).toHaveLength(1);
  });

  it("ignores events it has already seen (a reconnect replays from ?after=)", () => {
    const once = fold([ev(1, "session", { session_id: "s_1" }), ev(2, "cost", { usd_total: 0.01, tokens_total: 10 })]);
    const again = fold([ev(2, "cost", { usd_total: 9, tokens_total: 9 })], once);
    expect(again).toBe(once);
  });

  it("takes the ended run from the done event", () => {
    const done = run({ status: "finished", project_id: "p_1", session_id: "s_1", steps: STEP_KEYS.map((k) => step(k, "done", 0, 1)) });
    const s = fold([ev(1, "done", done as unknown as Record<string, unknown>)]);
    expect(s.final?.status).toBe("finished");
    expect(s.steps.every((x) => x.status === "done")).toBe(true);
    expect(s.sessionId).toBe("s_1");
  });
});

describe("autopilotView", () => {
  it("prefers the live stream while the run works, and the ended run once it ends", () => {
    const live = fold([ev(1, "step", { steps: [step("understand", "running", 0), ...pending().slice(1)] })]);
    expect(autopilotView(run(), live).steps[0].status).toBe("running");
    const ended = run({ status: "stopped", project_id: "p_1", session_id: "s_1", steps: STEP_KEYS.map((k) => step(k, "skipped")) });
    const v = autopilotView(ended, live);
    expect(v.status).toBe("stopped");
    expect(v.final?.id).toBe("ap_1");
    expect(v.steps.every((x) => x.status === "skipped")).toBe(true);
  });
});

describe("progress", () => {
  it("nothing yet: step 1, no progress", () => {
    expect(autopilotProgress(pending(), false)).toMatchObject({ percent: 0, current: null, stepN: 1, total: 8 });
  });

  it("counts finished and skipped steps and half of the running one", () => {
    const steps = pending();
    steps[0] = step("understand", "skipped");
    steps[1] = step("venue", "skipped");
    steps[2] = step("capacity", "skipped");
    steps[3] = step("simulate", "running", 10);
    const p = autopilotProgress(steps, false);
    expect(p.current?.key).toBe("simulate");
    expect(p.stepN).toBe(4);
    expect(p.percent).toBe(44); // (3 + 0.5) / 8
  });

  it("never claims 100% before the end, and is full once ended", () => {
    const steps = STEP_KEYS.map((k) => step(k, k === "deliver" ? "running" : "done"));
    expect(autopilotProgress(steps, false).percent).toBe(94);
    expect(autopilotProgress(steps, true).percent).toBe(100);
  });

  it("times running and finished steps, not pending ones", () => {
    expect(stepElapsed(step("simulate", "running", 20), now)).toBe(30);
    expect(stepElapsed(step("understand", "done", 0, 4), now)).toBe(4);
    expect(stepElapsed(step("fix", "pending"), now)).toBeNull();
  });
});

describe("where to go next", () => {
  it("opens Your plan with the tested session", () => {
    const done = run({ status: "finished", project_id: "p_1", session_id: "s_1" });
    expect(planHref(done)).toBe("/p/p_1?session=s_1");
    expect(opensPlan(done)).toBe(true);
    expect(opensPlan({ ...done, status: "stopped" })).toBe(true);
  });

  it("stays put when nothing was tested or the run failed", () => {
    expect(opensPlan(run({ status: "stopped", project_id: "p_1" }))).toBe(false);
    expect(planHref(run({ status: "stopped", project_id: "p_1" }))).toBe("/p/p_1");
    expect(opensPlan(run({ status: "failed", project_id: "p_1", session_id: "s_1" }))).toBe(false);
    expect(planHref(run({ status: "failed" }))).toBeNull();
  });

  it("tries the same request again", () => {
    expect(retryBody(run({ depth: "thorough" }))).toEqual({ text: "A concert for 400 people", depth: "thorough" });
    expect(retryBody(run({ text: null, project_id: "p_1" }))).toEqual({ project_id: "p_1", depth: "quick" });
  });
});
