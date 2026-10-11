import { describe, expect, it } from "vitest";
import { workSteps } from "@/journey/workSteps";

const at = (s: number) => new Date(Date.UTC(2026, 9, 11, 10, 0, s)).toISOString();
const now = Date.parse(at(50));

describe("workSteps", () => {
  it("nothing yet: every step pending", () => {
    expect(workSteps([], { ended: false, failed: false, now }).map((s) => s.status)).toEqual(["pending", "pending", "pending", "pending", "pending"]);
  });

  it("groups phases into steps and times them", () => {
    const h = [{ phase: "baseline", ts: at(0) }, { phase: "red_team", ts: at(10) }, { phase: "screening", ts: at(20) }];
    const s = workSteps(h, { ended: false, failed: false, now });
    expect(s.map((x) => x.status)).toEqual(["done", "running", "pending", "pending", "pending"]);
    expect(s[0].elapsedS).toBe(10);
    expect(s[1].elapsedS).toBe(40); // red_team 10 s + screening running for 30 s
  });

  it("a step the session jumped over is skipped, not pending", () => {
    // no breaks found: no fixes, straight to judging
    const h = [{ phase: "baseline", ts: at(0) }, { phase: "red_team", ts: at(5) }, { phase: "judging", ts: at(30) }];
    expect(workSteps(h, { ended: false, failed: false, now }).map((x) => x.status)).toEqual(["done", "done", "skipped", "skipped", "running"]);
  });

  it("finished: everything done or skipped, nothing running", () => {
    const h = [{ phase: "baseline", ts: at(0) }, { phase: "red_team", ts: at(5) }, { phase: "judging", ts: at(30) }, { phase: "done", ts: at(40) }];
    expect(workSteps(h, { ended: true, failed: false, now }).map((x) => x.status)).toEqual(["done", "done", "skipped", "skipped", "done"]);
  });

  it("marks the current step failed when the session failed", () => {
    const h = [{ phase: "baseline", ts: at(0) }];
    expect(workSteps(h, { ended: true, failed: true, now })[0].status).toBe("failed");
  });
});
