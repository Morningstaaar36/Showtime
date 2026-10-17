import { describe, expect, it } from "vitest";
import { scriptOf } from "@/journey/scriptSource";

const src = { incident: "x", source_url: "https://example.org" };

describe("scriptOf", () => {
  it("finds the script event of an AI-written attack", () => {
    const attack = {
      events: [{ type: "script", at_s: 0, title: "Gate jam", code: "def on_step(view, act):\n    pass\n", every_s: 2 }],
      extensions: {},
      inspired_by: src,
    };
    expect(scriptOf(attack)).toEqual({ title: "Gate jam", code: "def on_step(view, act):\n    pass\n", everyS: 2, author: "ai" });
  });

  it("labels the built-in example and ignores menu attacks", () => {
    expect(scriptOf({ events: [{ type: "script", at_s: 0, code: "x" }], extensions: { generated_by: "rules" } })?.author).toBe("rules");
    expect(scriptOf({ events: [{ type: "block_exit", at_s: 0, exit_id: "e1" }], extensions: {} })).toBeNull();
    expect(scriptOf(undefined)).toBeNull();
  });
});
