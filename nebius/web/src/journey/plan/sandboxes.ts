/** The plan page's "Sandboxes" view: every run of a test in its sandbox, and what happened to
 * each AI-written scenario script, from the session's own events. */
import type { Attack } from "@/api/types";
import type { SandboxRun, SessionView } from "@/api/useSessionStream";
import { scriptOf } from "@/journey/scriptSource";

/** The session's sandbox rows; a test from before the live feed existed gets rows built from
 * its finished runs (no times or script outcomes were recorded then). */
export function sandboxRows(view: Pick<SessionView, "sandboxes" | "runs" | "nodes">): { rows: SandboxRun[]; recorded: boolean } {
  if (view.sandboxes.length) return { rows: view.sandboxes, recorded: true };
  const label = new Map(Object.values(view.nodes).map((n) => [n.run_id, n.label]));
  const rows = Object.values(view.runs).map((r): SandboxRun => ({
    run_id: r.run_id,
    label: label.get(r.run_id) ?? r.run_id,
    state: r.status === "ok" || r.status === "partial" ? "finished" : r.status === "timeout" ? "killed" : "failed",
    elapsed_s: Number.NaN,
    tier: r.tier,
    provider: r.provider,
  }));
  return { rows, recorded: false };
}

export interface ScriptOutcome { attack: Attack; run: SandboxRun | null }

/** Every AI-written scenario of the test, with its sandbox run (null when it has none yet). */
export function scriptOutcomes(view: Pick<SessionView, "sandboxes" | "nodes">, attacks: Attack[]): ScriptOutcome[] {
  const byRun = new Map(view.sandboxes.map((r) => [r.run_id, r]));
  return attacks.filter((a) => scriptOf(a)).map((attack) => {
    const node = Object.values(view.nodes).find((n) => n.kind === "attack" && n.attack_id === attack.attack_id && !n.node_id.includes(":current:"));
    return { attack, run: node ? byRun.get(node.run_id) ?? null : null };
  });
}
