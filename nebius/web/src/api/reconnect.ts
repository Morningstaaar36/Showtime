/** Backoff for the SSE hooks: a dropped stream retries after 2 s, then waits longer each
 *  consecutive failure (capped at 30 s) and gives up after MAX_RECONNECTS (e.g. a 404 session).
 *  Callers reset their failure count whenever the stream opens or delivers an event. */
export const MAX_RECONNECTS = 8;

/** Delay before reconnect attempt `failures` (1 = first failure in a row), or null to stop. */
export function reconnectDelay(failures: number): number | null {
  if (failures < 1 || failures > MAX_RECONNECTS) return null;
  return Math.min(30_000, 2000 * 2 ** (failures - 1));
}
