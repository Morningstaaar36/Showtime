/** "How this plan was made" (N16): the session's measured cost record in organizer words. */
import { t } from "@/i18n";
import type { CostRecord } from "@/lib/evidence";
import { fmtDuration, fmtInt, fmtMoney, fmtTokens } from "@/lib/format";

export interface CostView {
  /** AI model cost; free and local models are "$0.00" */
  total: string;
  free: boolean;
  calls: string;
  models: { name: string; detail: string }[];
  sims: string;
  /** simulations that did not finish, and reused ones (empty when none) */
  simsNote: string;
  compute: string;
  wall: string;
}

function count(key: string, n: number): string | null {
  if (!n) return null;
  return n === 1 ? t(`${key}_one`) : t(key, { n: fmtInt(n) });
}

export function costView(cost: CostRecord | null | undefined): CostView | null {
  if (!cost) return null;
  const usd = Number(cost.usd_total) || 0;
  const sims = cost.sims ?? { instant_estimates: 0, quick_sims: 0, full_sims: 0, failed: 0, cache_hits: 0, sim_seconds: 0 };
  const calls = t("yourplan.cost_calls_value", { n: fmtInt(cost.calls), tin: fmtTokens(cost.tokens_in), tout: fmtTokens(cost.tokens_out) });
  const cached = cost.llm_cache_hits ? ` · ${t("yourplan.cost_cache", { n: fmtInt(cost.llm_cache_hits) })}` : "";
  const models = Object.entries(cost.by_model ?? {})
    .sort((a, b) => b[1].calls - a[1].calls || a[0].localeCompare(b[0]))
    .map(([name, b]) => ({
      name,
      detail: `${count("yourplan.calls", b.calls) ?? t("yourplan.calls", { n: 0 })} · ${fmtTokens(b.tokens_in + b.tokens_out)} tokens · ${fmtMoney(b.usd)}`,
    }));
  const kinds = [count("yourplan.cost_full", sims.full_sims), count("yourplan.cost_quick", sims.quick_sims),
    count("yourplan.cost_instant", sims.instant_estimates)].filter(Boolean);
  const notes = [sims.failed ? t("yourplan.cost_failed", { n: fmtInt(sims.failed) }) : null,
    sims.cache_hits ? t("yourplan.cost_reused", { n: fmtInt(sims.cache_hits) }) : null].filter(Boolean);
  return {
    total: fmtMoney(usd),
    free: usd === 0,
    calls: calls + cached,
    models,
    sims: kinds.length ? kinds.join(" · ") : t("yourplan.cost_none"),
    simsNote: notes.join(" · "),
    compute: fmtDuration(sims.sim_seconds),
    wall: fmtDuration(cost.wall_s),
  };
}
