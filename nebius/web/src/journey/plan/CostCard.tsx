/** "How this plan was made" (N16): measured model cost, models, simulations by kind, compute
 * and wall time of the test behind this plan. Free and local models cost "$0.00". */
import { t } from "@/i18n";
import type { CostRecord } from "@/lib/evidence";
import { fmtMoney, fmtTokens } from "@/lib/format";
import { costView } from "./cost";

export function CostCard({ cost, tokens, costUsd }: { cost: CostRecord | null | undefined; tokens: number; costUsd: number }) {
  const v = costView(cost);
  return (
    <section aria-labelledby="cost-h" className="space-y-2 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
      <h2 id="cost-h" className="font-semibold">{t("yourplan.cost")}</h2>
      {!v ? (
        <p className="text-sm text-muted">{tokens ? t("yourplan.cost_tokens_only", { tokens: fmtTokens(tokens), cost: fmtMoney(costUsd) }) : t("yourplan.cost_missing")}</p>
      ) : (
        <>
          <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted">{t("yourplan.cost_total")}</dt>
              <dd className="text-lg font-semibold tabular">{v.total}{v.free && <span className="ml-1.5 text-sm font-normal text-muted">({t("yourplan.cost_free")})</span>}</dd>
            </div>
            <div>
              <dt className="text-muted">{t("yourplan.cost_calls")}</dt>
              <dd className="tabular">{v.calls}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-muted">{t("yourplan.cost_sims")}</dt>
              <dd className="tabular">{v.sims}{v.simsNote && <span className="text-muted"> ({v.simsNote})</span>}</dd>
            </div>
            <div>
              <dt className="text-muted">{t("yourplan.cost_compute")}</dt>
              <dd className="tabular">{v.compute}</dd>
            </div>
            <div>
              <dt className="text-muted">{t("yourplan.cost_wall")}</dt>
              <dd className="tabular">{v.wall}</dd>
            </div>
            {v.models.length > 0 && (
              <div className="sm:col-span-2">
                <dt className="text-muted">{t("yourplan.cost_models")}</dt>
                <dd>
                  <ul className="space-y-0.5">
                    {v.models.map((m) => <li key={m.name} className="flex flex-wrap justify-between gap-x-3"><span className="min-w-0 break-all">{m.name}</span><span className="text-muted tabular">{m.detail}</span></li>)}
                  </ul>
                </dd>
              </div>
            )}
          </dl>
          <p className="text-xs text-muted">{t("yourplan.cost_body")}</p>
        </>
      )}
    </section>
  );
}
