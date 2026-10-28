/** How often the page re-reads a record while the server is still working on it, in one place
 * so the load on the API is easy to see and tune. Each poll stops once the record is finished. */

/** Health and provider status: it changes only when a service starts or stops. */
export const HEALTH_POLL_MS = 15_000;
/** A single run: the progress bar and the replay wait on it, and the read is cheap. */
export const RUN_POLL_MS = 1000;
/** Sessions and Autopilot runs: their event streams carry the progress, so this only catches
 * up when a stream drops. */
export const SESSION_POLL_MS = 3000;
/** Rewind, stress, sensitivity and "together" checks: a few branch runs of a few seconds each. */
export const CHECK_POLL_MS = 1500;
/** Seed checks and scenario sweeps: many sandbox runs at once that finish over minutes. */
export const SWEEP_POLL_MS = 2500;
