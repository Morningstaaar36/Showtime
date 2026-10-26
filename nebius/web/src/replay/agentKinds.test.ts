import { afterEach, describe, expect, it, vi } from "vitest";

// who each simulated person is: asked for only when the run's own record lists the file, so a run
// without it never causes a 404 (which the browser logs as an error)
const get = vi.fn();
vi.mock("@/api/client", () => ({ api: { get: (...a: unknown[]) => get(...a) } }));

afterEach(() => get.mockReset());

describe("agent kinds of a run", () => {
  it("asks for the file only when the run lists it", async () => {
    const { agentKinds } = await import("./useReplay");
    get.mockImplementation(async (path: string) => (path.endsWith("/agents") ? { schema: 1, kinds: [] } : { result: { artifacts: { agents: null } } }));
    expect(await agentKinds("r_1", new AbortController().signal)).toBeNull();
    expect(get.mock.calls.map((c) => c[0])).toEqual(["/runs/r_1"]);
  });
  it("reads the file when the run has one", async () => {
    const { agentKinds } = await import("./useReplay");
    get.mockImplementation(async (path: string) => (path.endsWith("/agents") ? { schema: "showtime.agents/1", kinds: ["general", "child"], index: [] } : { result: { artifacts: { agents: "runs/r_2/agents.json" } } }));
    await agentKinds("r_2", new AbortController().signal);
    expect(get.mock.calls.map((c) => c[0])).toEqual(["/runs/r_2", "/runs/r_2/agents"]);
  });
});
