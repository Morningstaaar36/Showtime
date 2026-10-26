import { describe, expect, it } from "vitest";
import { EMPTY, reduce, sandboxCounts, type SessionView } from "./useSessionStream";
import type { SessionEvent } from "./types";

let seq = 0;
const ev = (payload: Record<string, unknown>): SessionEvent =>
  ({ seq: ++seq, type: "sandbox", ts: "2026-10-25T10:00:00Z", payload }) as unknown as SessionEvent;
const fold = (events: SessionEvent[], from: SessionView = EMPTY) => events.reduce((s, e) => reduce(s, { kind: "event", ev: e }), from);

describe("the sandbox feed in the session stream", () => {
  it("keeps one row per run, updated in place, in start order", () => {
    const s = fold([
      ev({ run_id: "r1", label: "Baseline", state: "queued", elapsed_s: 0 }),
      ev({ run_id: "r2", label: "Smoke spreads", state: "queued", elapsed_s: 0 }),
      ev({ run_id: "r1", label: "Baseline", state: "running", elapsed_s: 0.4 }),
      ev({ run_id: "r1", label: "Baseline", state: "finished", elapsed_s: 12.3 }),
      ev({ run_id: "r2", label: "Smoke spreads", state: "refused", elapsed_s: 0.8,
           reason: "it failed the safety check (import of 'socket' is not allowed)", script: { state: "refused", reason: "it failed the safety check" } }),
    ]);
    expect(s.sandboxes.map((r) => [r.run_id, r.state])).toEqual([["r1", "finished"], ["r2", "refused"]]);
    expect(s.sandboxes[1].reason).toMatch(/socket/);
    expect(sandboxCounts(s.sandboxes)).toEqual({ queued: 0, running: 0, done: 2, stopped: 1, total: 2 });
  });
  it("counts what is still waiting and running", () => {
    const s = fold([ev({ run_id: "a", label: "A", state: "running", elapsed_s: 1 }), ev({ run_id: "b", label: "B", state: "queued", elapsed_s: 0 })]);
    expect(sandboxCounts(s.sandboxes)).toMatchObject({ queued: 1, running: 1, done: 0, total: 2 });
  });
});
