/** Backoff for the SSE hooks: a dropped stream retries after 2 s, then waits longer each
 *  consecutive failure (capped at 30 s) and gives up after MAX_RECONNECTS (e.g. a 404 session).
 *  Callers reset their failure count whenever the stream opens or delivers an event. */
export const MAX_RECONNECTS = 8;

/** Delay before reconnect attempt `failures` (1 = first failure in a row), or null to stop. */
export function reconnectDelay(failures: number): number | null {
  if (failures < 1 || failures > MAX_RECONNECTS) return null;
  return Math.min(30_000, 2000 * 2 ** (failures - 1));
}

export interface StreamHandlers<E> {
  event: (ev: E) => void;
  conn: (open: boolean) => void;
  /** the server ended the stream, or reconnecting gave up: either way nothing more will come */
  end: () => void;
}

/** Follow an SSE stream, reopening it with backoff when it drops. `url` is read on every
 * (re)connect so the caller can resume after the last event it saw. Returns the close function
 * for an effect's cleanup. */
export function followStream<E>(url: () => string, on: StreamHandlers<E>): () => void {
  let es: EventSource | null = null;
  let closed = false;
  let retry: number | undefined;
  let failures = 0;
  const open = () => {
    es = new EventSource(url());
    // only a delivered event proves the stream works: a stream that opens and drops at once
    // must still back off
    es.onopen = () => on.conn(true);
    es.onmessage = (m) => {
      failures = 0;
      let ev: E;
      try {
        ev = JSON.parse(m.data as string) as E;
      } catch {
        return; // ignore malformed lines
      }
      on.event(ev);
    };
    es.addEventListener("end", () => {
      closed = true;
      es?.close();
      on.end();
    });
    es.onerror = () => {
      es?.close();
      on.conn(false);
      const wait = closed ? null : reconnectDelay(++failures);
      if (wait != null) retry = window.setTimeout(open, wait);
      // given up: stop waiting on the stream (the page re-reads the record from the API)
      else if (!closed) {
        closed = true;
        on.end();
      }
    };
  };
  open();
  return () => {
    closed = true;
    if (retry) window.clearTimeout(retry);
    es?.close();
  };
}
