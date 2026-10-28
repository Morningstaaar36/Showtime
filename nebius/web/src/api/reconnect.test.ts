import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MAX_RECONNECTS, followStream, reconnectDelay } from "./reconnect";

describe("reconnectDelay", () => {
  it("retries a first drop after 2 s and backs off up to 30 s", () => {
    expect([1, 2, 3, 4, 5, 6].map(reconnectDelay)).toEqual([2000, 4000, 8000, 16000, 30000, 30000]);
  });
  it("gives up after the last allowed attempt", () => {
    expect(reconnectDelay(MAX_RECONNECTS)).toBe(30000);
    expect(reconnectDelay(MAX_RECONNECTS + 1)).toBeNull();
    expect(reconnectDelay(0)).toBeNull();
  });
});

/** Just enough of EventSource to drive the helper by hand (jsdom has none). */
class FakeSource {
  static all: FakeSource[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private listeners: Record<string, () => void> = {};
  constructor(readonly url: string) { FakeSource.all.push(this); }
  addEventListener(name: string, fn: () => void) { this.listeners[name] = fn; }
  close() { this.closed = true; }
  emit(name: string) { this.listeners[name]?.(); }
}

describe("followStream", () => {
  beforeEach(() => {
    FakeSource.all = [];
    vi.useFakeTimers();
    vi.stubGlobal("EventSource", FakeSource);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  const follow = () => {
    let after = 0;
    const on = { event: vi.fn((ev: { seq: number }) => { after = ev.seq; }), conn: vi.fn(), end: vi.fn() };
    const close = followStream(() => `/events?after=${after}`, on);
    return { on, close };
  };

  it("passes parsed events on, skips malformed lines and resumes after the last one", () => {
    const { on } = follow();
    const first = FakeSource.all[0];
    first.onopen?.();
    first.onmessage?.({ data: '{"seq":3}' });
    first.onmessage?.({ data: "not json" });
    first.onerror?.();
    expect(on.event).toHaveBeenCalledTimes(1);
    expect(on.conn.mock.calls).toEqual([[true], [false]]);
    vi.advanceTimersByTime(2000);
    expect(FakeSource.all[1].url).toBe("/events?after=3");
  });

  it("ends once when the server ends the stream, and does not reopen", () => {
    const { on } = follow();
    FakeSource.all[0].emit("end");
    FakeSource.all[0].onerror?.();
    vi.runAllTimers();
    expect(on.end).toHaveBeenCalledTimes(1);
    expect(FakeSource.all).toHaveLength(1);
  });

  it("ends when it gives up reconnecting", () => {
    const { on } = follow();
    for (let i = 0; i <= MAX_RECONNECTS; i++) {
      FakeSource.all.at(-1)?.onerror?.();
      vi.runAllTimers();
    }
    expect(FakeSource.all).toHaveLength(MAX_RECONNECTS + 1);
    expect(on.end).toHaveBeenCalledTimes(1);
  });

  it("stops reconnecting once closed", () => {
    const { close } = follow();
    FakeSource.all[0].onerror?.();
    close();
    vi.runAllTimers();
    expect(FakeSource.all).toHaveLength(1);
  });
});
