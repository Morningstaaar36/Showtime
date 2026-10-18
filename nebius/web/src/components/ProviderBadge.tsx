import { Cloud, Coins, Cpu } from "lucide-react";
import { Link } from "react-router";
import { useHealth } from "@/api/queries";
import type { ProviderStatus } from "@/api/types";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { t } from "@/i18n";
import { fmtMoney, fmtTokens } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Where the AI runs, in plain words ("AI runs on this computer"). */
export function providerWhere(llm: ProviderStatus | undefined): string {
  if (llm?.provider === "nebius") return t("common.provider_nebius");
  if (llm?.provider === "openai") return t("common.provider_cloud", { label: llm.label ?? "CLOUD" });
  return t("common.provider_local");
}

/** LOCAL / NEBIUS / cloud badge. A click (or tap) opens what it means, the AI and simulator
 * status, and, in Expert view, the project's AI cost. */
export function ProviderBadge({ cost }: { cost?: { tokens: number; usd: number } | null }) {
  const { data } = useHealth();
  const llm = data?.providers.llm;
  const sandbox = data?.providers.sandbox;
  const cloud = llm?.provider === "nebius" || llm?.provider === "openai";
  const label = llm?.label ?? (cloud ? "CLOUD" : "LOCAL");
  const ok = llm?.ok ?? false;
  const fallback = !!(llm as { fallback?: boolean } | undefined)?.fallback;
  const Icon = cloud ? Cloud : Cpu;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" aria-label={t("common.provider_aria", { label })}
                className={cn("inline-flex h-8 items-center whitespace-nowrap gap-1.5 rounded-[var(--radius-control)] border px-2 text-2xs font-semibold tracking-wide transition-colors hover:border-border-strong",
                  ok ? "border-border bg-surface text-ink" : "border-caution/40 bg-caution-soft text-ink")}>
          <Icon className="size-3.5" aria-hidden />
          {label}{fallback && <span className="font-normal text-muted">→ LOCAL</span>}
          <span aria-hidden className={cn("size-1.5 rounded-full", ok && !fallback ? "bg-egress" : "bg-caution")} />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 space-y-3">
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-full bg-signal-soft text-signal [&_svg]:size-5"><Icon aria-hidden /></span>
          <div className="min-w-0">
            <p className="font-semibold leading-snug">{providerWhere(llm)}</p>
            <p className="mt-0.5 break-words text-xs text-muted">{llm?.detail ?? t("common.provider_checking")}</p>
          </div>
        </div>
        <dl className="space-y-1.5 rounded-[var(--radius-control)] bg-surface-2 p-3">
          <StatusRow name={t("common.provider_ai")} ok={ok && !fallback}
                     value={!data ? t("common.provider_checking") : fallback ? t("common.provider_backup") : ok ? t("common.provider_ready") : t("common.provider_not_ready")} />
          <StatusRow name={t("common.provider_sim")} ok={!!sandbox?.ok}
                     value={!data ? t("common.provider_checking") : sandbox?.ok ? t("common.provider_ready") : t("common.provider_not_ready")} />
        </dl>
        <p className="text-xs text-muted">{t("common.provider_dots")}</p>
        {cost && (
          <div className="border-t border-border pt-3">
            <p className="flex items-center gap-1.5 text-sm font-semibold"><Coins className="size-4 text-orange" aria-hidden />{t("common.cost_title")}</p>
            <p className="mt-0.5 text-lg font-bold tabular">{t("common.cost_value", { tokens: fmtTokens(cost.tokens), usd: fmtMoney(cost.usd) })}</p>
            <p className="text-xs text-muted">{t("common.cost_hint")}</p>
          </div>
        )}
        <Link to="/settings" className="inline-flex min-h-9 items-center text-sm font-medium text-signal hover:underline">{t("common.provider_more")}</Link>
      </PopoverContent>
    </Popover>
  );
}

function StatusRow({ name, value, ok }: { name: string; value: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <dt className="text-muted">{name}</dt>
      <dd className="flex items-center gap-1.5 font-medium">
        <span aria-hidden className={cn("size-2 rounded-full", ok ? "bg-egress" : "bg-caution")} />{value}
      </dd>
    </div>
  );
}
