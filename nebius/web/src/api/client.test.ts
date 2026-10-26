import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, configureTimeouts, errorText, REQUEST_TIMEOUT_MS } from "@/api/client";

/** A fetch that never answers until its signal aborts it. */
function hangingFetch() {
  return vi.fn((_url: string, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  }));
}

describe("request timeout", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("gives up on a read that never answers, with a clear error", async () => {
    vi.stubGlobal("fetch", hangingFetch());
    const p = api.get("/health");
    const settled = p.catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS.read + 10);
    const err = await settled;
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("timeout");
    expect((err as ApiError).message).toMatch(/took too long/);
  });

  it("gives a write (an agent at work) more time than a read", async () => {
    vi.stubGlobal("fetch", hangingFetch());
    let done = false;
    const p = api.post("/venues/design", { text: "a hall" }).catch((e: unknown) => { done = true; return e; });
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS.read + 10);
    expect(done).toBe(false);
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS.write);
    expect(((await p) as ApiError).code).toBe("timeout");
  });

  it("keeps the caller's own cancel as a cancel, not a timeout", async () => {
    vi.stubGlobal("fetch", hangingFetch());
    const ctrl = new AbortController();
    const p = api.get("/health", ctrl.signal).catch((e: unknown) => e);
    ctrl.abort();
    const err = await p;
    expect((err as Error).name).toBe("AbortError");
  });
});

describe("timeouts come from the server", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); configureTimeouts({ read_timeout_s: 60, write_timeout_s: 330 }); });

  it("uses WEB_READ_TIMEOUT_S once /health has sent it", async () => {
    configureTimeouts({ read_timeout_s: 2, write_timeout_s: 9 });
    expect(REQUEST_TIMEOUT_MS).toEqual({ read: 2000, write: 9000 });
    vi.stubGlobal("fetch", hangingFetch());
    const p = api.get("/projects").catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(2010);
    expect(((await p) as ApiError).message).toMatch(/over 2 s/);
  });
  it("ignores a missing or nonsense value", () => {
    configureTimeouts(undefined);
    configureTimeouts({ read_timeout_s: 0 });
    expect(REQUEST_TIMEOUT_MS.read).toBe(60_000);
  });
});

describe("errorText", () => {
  it("adds the API's hint to its message, so a toast says what to do", () => {
    expect(errorText(new ApiError(503, "llm_unavailable", "The language model isn't answering.", "OPENROUTER rejected the API key (HTTP 401)."))).toBe(
      "The language model isn't answering. OPENROUTER rejected the API key (HTTP 401).");
    expect(errorText(new Error("Network down"))).toBe("Network down");
  });
});
