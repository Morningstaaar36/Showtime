/** "How this plan was made" (N16): measured model cost, models, simulations by kind, compute
 * and wall time of the test behind this plan, as tiles. Free and local models cost "$0.00". */
import { Bot, Clock3, Cpu, Sparkles, Timer } from "lucide-react";
import type * as React from "react";
import { t } from "@/i18n";
import type { CostRecord } from "@/lib/evidence";
import { fmtMoney, fmtTokens } from "@/lib/format";
import { costView } from "./cost";

function Stat({ icon, label, value, note }: { icon: React.ReactNode; label: string; value: string; note?: string }) {
  return (
    <div className="flex min-w-0 items-start gap-2.5 rounded-[10px] bg-surface-2 p-3">
      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-surface text-signal [&_svg]:size-4" aria-hidden>{icon}</span>
      <div className="min-w-0">
        <dt className="text-xs text-muted">{label}</dt>
        <dd className="text-lg font-bold leading-tight tabular">{value}</dd>
        {note && <dd className="text-2xs text-muted">{note}</dd>}
      </div>
    </div>
  );
}

export function CostCard({ cost, tokens, costUsd }: { cost: CostRecord | null | undefined; tokens: number; costUsd: number }) {
  const v = costView(cost);
  return (
    <section aria-labelledby="cost-h" className="space-y-3 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
      <h2 id="cost-h" className="flex items-center gap-2 font-semibold"><Sparkles className="size-4 text-signal" aria-hidden />{t("yourplan.cost")}</h2>
      {!v ? (
        <p className="text-sm text-muted">{tokens ? t("yourplan.cost_tokens_only", { tokens: fmtTokens(tokens), cost: fmtMoney(costUsd) }) : t("yourplan.cost_missing")}</p>
      ) : (
        <>
          <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Stat icon={<Bot />} label={t("yourplan.cost_total")} value={v.total} note={v.free ? t("yourplan.cost_free") : undefined} />
            <Stat icon={<Cpu />} label={t("yourplan.cost_sims")} value={v.sims.split(" · ")[0]} note={[...v.sims.split(" · ").slice(1), v.simsNote].filter(Boolean).join(" · ") || undefined} />
            <Stat icon={<Timer />} label={t("yourplan.cost_compute")} value={v.compute} />
            <Stat icon={<Clock3 />} label={t("yourplan.cost_wall")} value={v.wall} />
          </dl>
          <details className="text-sm">
            <summary className="flex min-h-9 cursor-pointer items-center text-xs font-medium text-signal">{t("plan.cost_more")}</summary>
            <dl className="mt-1 space-y-1">
              <div className="flex flex-wrap justify-between gap-x-3"><dt className="text-muted">{t("yourplan.cost_calls")}</dt><dd className="tabular">{v.calls}</dd></div>
              {v.models.map((m) => <div key={m.name} className="flex flex-wrap justify-between gap-x-3"><dt className="min-w-0 break-all">{m.name}</dt><dd className="text-muted tabular">{m.detail}</dd></div>)}
            </dl>
            <p className="mt-2 text-xs text-muted">{t("yourplan.cost_body")}</p>
          </details>
        </>
      )}
    </section>
  );
}
