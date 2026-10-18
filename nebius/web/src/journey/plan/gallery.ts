/** Scenario cards for Your plan › Scenarios: a short headline from what the scenario does (≤ 5
 * words), an icon per kind of event, and the stress test at scale counted per attack. Pure. */
import type { Attack } from "@/api/types";
import { t } from "@/i18n";
import { type StressRecord, rowOutcome } from "./stress";

export type ScenarioKind = "block" | "surge" | "slow" | "counter" | "hold" | "script" | "normal" | "other";

type Ev = { type?: string; [k: string]: unknown };

const KIND: Record<string, ScenarioKind> = {
  block_exit: "block", surge: "surge", slowdown: "slow", counterflow: "counter", staggered_release: "hold", script: "script",
};

/** The kind of the scenario's first event (what makes it a scenario). */
export function scenarioKind(attack: Pick<Attack, "events"> | null | undefined): ScenarioKind {
  if (!attack) return "normal";
  const ev = ((attack.events ?? []) as Ev[]).find((e) => e.type && KIND[e.type]);
  return ev?.type ? KIND[ev.type] : "other";
}

/** "East exit blocked", "Surge into Ward A": what the scenario does, from its first event. */
export function scenarioHeadline(attack: Pick<Attack, "events" | "title"> | null | undefined, name: (id: string) => string): string {
  if (!attack) return t("plan.sc_normal");
  const evs = (attack.events ?? []) as Ev[];
  const ev = evs.find((e) => e.type && KIND[e.type]) ?? evs[0];
  const s = (k: string) => (typeof ev?.[k] === "string" ? name(ev[k] as string) : "");
  switch (ev?.type) {
    case "block_exit": return t("plan.sc_block", { exit: s("exit_id") });
    case "surge": return t("plan.sc_surge", { zone: s("zone_id") });
    case "slowdown": return t("plan.sc_slow");
    case "counterflow": return t("plan.sc_counter", { exit: s("exit_id") });
    case "staggered_release": return t("plan.sc_hold", { zone: s("zone_id") });
    case "script": return t("plan.sc_script");
    default: return attack.title.split(/\s+/).slice(0, 5).join(" ");
  }
}

export interface StressCount { runs: number; breaks: number }

/** Finished stress runs of each attack, on the plan as it is (not with a single change). */
export function stressByAttack(rec: StressRecord | null | undefined): Map<string, StressCount> {
  const out = new Map<string, StressCount>();
  for (const row of rec?.rows ?? []) {
    if (row.fix_id) continue;
    const o = rowOutcome(row);
    if (o !== "breaks" && o !== "holds") continue;
    const c = out.get(row.attack_id) ?? { runs: 0, breaks: 0 };
    c.runs += 1;
    if (o === "breaks") c.breaks += 1;
    out.set(row.attack_id, c);
  }
  return out;
}
