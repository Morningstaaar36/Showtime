/** How deep a test goes ("Test this plan" and "Test again"): the session settings behind each
 * mode, from GET /test_modes (api/data/test_modes.json). Every mode simulates every attack and
 * fix; they differ in how many rounds the red team gets and whether the AI designs the attacks
 * and fixes. The choice is remembered per browser. */

export interface TestModeInfo {
  id: string;
  /** about how long a local run takes, for the hint */
  minutes: number;
  config: Record<string, unknown>;
}

export interface TestModes {
  default: string;
  modes: readonly TestModeInfo[];
}

/** Used only until GET /test_modes answers (or against an older server), so the picker is never
 * empty: the same four modes as api/data/test_modes.json. */
const FALLBACK: TestModes = {
  default: "standard",
  modes: [
    { id: "quick", minutes: 1, config: { max_rounds: 1, attacks_per_round: 2, fixes_per_attack: 1, fix_targets: 1, agents: "model" } },
    { id: "standard", minutes: 3, config: { max_rounds: 1, attacks_per_round: 3, fixes_per_attack: 2, fix_targets: 2, agents: "model" } },
    { id: "deep", minutes: 10, config: { max_rounds: 3, attacks_per_round: 3, fixes_per_attack: 2, fix_targets: 2, agents: "model", confirm_tier3: true } },
    { id: "offline", minutes: 3, config: { max_rounds: 1, attacks_per_round: 3, fixes_per_attack: 2, fix_targets: 2, agents: "rules" } },
  ],
};

/** The server's modes when it sent a usable list, else the fallback. */
export function testModesOf(out: TestModes | undefined): TestModes {
  const modes = (out?.modes ?? []).filter((m) => m && typeof m.id === "string" && typeof m.minutes === "number" && typeof m.config === "object");
  return modes.length ? { default: out?.default ?? FALLBACK.default, modes } : FALLBACK;
}

/** The mode `id`, or the default one when there is no such mode. */
export function testMode(id: string | null | undefined, modes: TestModes): TestModeInfo {
  return modes.modes.find((m) => m.id === id) ?? modes.modes.find((m) => m.id === modes.default) ?? modes.modes[0];
}

const KEY = "showtime.testMode";

/** The id this browser used last, as stored: it may name a mode that only the server knows, so
 * it is resolved against the list when the list is there. Null when none or storage is blocked. */
export function savedTestModeId(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** The mode this browser used last (the default when none, or when storage is unavailable). */
export const savedTestMode = (modes: TestModes): TestModeInfo => testMode(savedTestModeId(), modes);

export function saveTestMode(id: string): void {
  try {
    window.localStorage.setItem(KEY, id);
  } catch {
    /* private window or blocked storage: the choice lasts for this page only */
  }
}
