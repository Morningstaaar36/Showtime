import { describe, expect, it } from "vitest";
import { sandboxWhy } from "./SandboxFeed";

const run = { run_id: "r1", label: "Smoke spreads", elapsed_s: 1 };

describe("why a sandbox run stopped", () => {
  it("quotes the in-sandbox check for a refused script", () => {
    expect(sandboxWhy({ ...run, state: "refused", script: { state: "refused", reason: "it failed the safety check (import of 'socket' is not allowed)" } }))
      .toEqual({ text: "AI-written script refused: it failed the safety check (import of 'socket' is not allowed)", tone: "danger" });
  });
  it("quotes the budget that stopped a script, while the run itself finished", () => {
    expect(sandboxWhy({ ...run, state: "finished", script: { state: "stopped", reason: "one step ran more than 200,000 lines" } })?.text)
      .toBe("AI-written script stopped: one step ran more than 200,000 lines");
  });
  it("calls a crash in the AI's own code an error, not a limit", () => {
    expect(sandboxWhy({ ...run, state: "finished", script: { state: "error", reason: "ValueError on line 5: max() iterable argument is empty" } }))
      .toEqual({ text: "AI-written script failed with an error in its own code: ValueError on line 5: max() iterable argument is empty", tone: "caution" });
  });
  it("says when a sandbox stopped and its run was started again", () => {
    expect(sandboxWhy({ ...run, state: "finished", retried: "The simulation crashed (exit 137): killed" }))
      .toEqual({ text: "The first sandbox stopped (The simulation crashed (exit 137): killed); the run started again in a new one and finished.", tone: "caution" });
  });
  it("says why a run was killed, and nothing for a clean run", () => {
    expect(sandboxWhy({ ...run, state: "killed", reason: "Stopped after 240 s of wall-clock time." })).toEqual({ text: "Stopped after 240 s of wall-clock time.", tone: "danger" });
    expect(sandboxWhy({ ...run, state: "finished", script: { state: "ran", reason: null } })).toBeNull();
  });
});
