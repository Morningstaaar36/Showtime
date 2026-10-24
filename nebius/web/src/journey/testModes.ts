/** How deep a test goes ("Test this plan" and "Test again"): the session settings behind each
 * mode. Every mode simulates every attack and fix; they differ in how many rounds the red team
 * gets and whether the AI designs the attacks and fixes. The choice is remembered per browser. */

export type TestMode = "quick" | "standard" | "deep" | "offline";

export interface TestModeInfo {
  id: TestMode;
  /** about how long a local run takes, for the hint */
  minutes: number;
  config: Record<string, unknown>;
}

export const TEST_MODES: readonly TestModeInfo[] = [
  // one round, a few attacks: a first look in about a minute
  { id: "quick", minutes: 1, config: { max_rounds: 1, attacks_per_round: 2, fixes_per_attack: 1, fix_targets: 1, agents: "model" } },
  // one round, the AI's attacks and fixes (the default)
  { id: "standard", minutes: 3, config: { max_rounds: 1, attacks_per_round: 3, fixes_per_attack: 2, fix_targets: 2, agents: "model" } },
  // three rounds on the improved plan: the failure map fills in, every finding confirmed in full
  { id: "deep", minutes: 10, config: { max_rounds: 3, attacks_per_round: 3, fixes_per_attack: 2, fix_targets: 2, agents: "model", confirm_tier3: true } },
  // no language model at all: rule-based attacks and standard fixes (no key, or offline)
  { id: "offline", minutes: 3, config: { max_rounds: 1, attacks_per_round: 3, fixes_per_attack: 2, fix_targets: 2, agents: "rules" } },
];

const KEY = "showtime.testMode";

export function testMode(id: string | null | undefined): TestModeInfo {
  return TEST_MODES.find((m) => m.id === id) ?? TEST_MODES[1];
}

/** The mode this browser used last (standard when none, or when storage is unavailable). */
export function savedTestMode(): TestModeInfo {
  try {
    return testMode(window.localStorage.getItem(KEY));
  } catch {
    return TEST_MODES[1];
  }
}

export function saveTestMode(id: TestMode): void {
  try {
    window.localStorage.setItem(KEY, id);
  } catch {
    /* private window or blocked storage: the choice lasts for this page only */
  }
}
