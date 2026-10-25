import { Check, Minus, ShieldCheck, ShieldOff } from "lucide-react";
import { Link } from "react-router";
import { useHealth } from "@/api/queries";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { sandboxFacts } from "./sandboxFacts";

/** Where the simulations and the AI's code run, next to the AI badge: the sandbox provider and,
 * on click, what it guarantees for every run (from GET /health). */
export function SandboxBadge() {
  const { data } = useHealth();
  const sb = data?.providers.sandbox;
  const iso = sb?.isolation;
  const none = iso?.kind === "none";
  const label = (sb?.provider ?? "sandbox").toUpperCase();
  const ok = !!sb?.ok && !none;
  const Icon = none ? ShieldOff : ShieldCheck;
  const facts = sandboxFacts(iso, sb?.time_limit_s);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" aria-label={t("common.sandbox_aria", { label })} data-testid="sandbox-badge"
                className={cn("inline-flex h-8 items-center whitespace-nowrap gap-1.5 rounded-[var(--radius-control)] border px-2 text-2xs font-semibold tracking-wide transition-colors hover:border-border-strong",
                  ok ? "border-border bg-surface text-ink" : "border-caution/40 bg-caution-soft text-ink")}>
          <Icon className="size-3.5" aria-hidden />
          {label}
          <span aria-hidden className={cn("size-1.5 rounded-full", ok ? "bg-egress" : "bg-caution")} />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 space-y-3">
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-full bg-egress-soft text-egress-strong [&_svg]:size-5"><Icon aria-hidden /></span>
          <div className="min-w-0">
            <p className="font-semibold leading-snug">{none ? t("common.sandbox_none_title") : t("common.sandbox_title")}</p>
            <p className="mt-0.5 break-words text-xs text-muted">{sb?.detail ?? t("common.provider_checking")}</p>
          </div>
        </div>
        {!none && <p className="text-xs">{t("common.sandbox_why")}</p>}
        {facts.length > 0 && (
          <ul className="space-y-1 rounded-[var(--radius-control)] bg-surface-2 p-3 text-sm" data-testid="sandbox-facts">
            {facts.map((f) => (
              <li key={f.key} className="flex items-center gap-2">
                {f.ok ? <Check className="size-4 shrink-0 text-egress" aria-hidden /> : <Minus className="size-4 shrink-0 text-caution" aria-hidden />}
                {f.text}
              </li>
            ))}
          </ul>
        )}
        {iso && !iso.per_job_limits && !none && <p className="text-xs text-muted">{t("common.sandbox_cloud_note")}</p>}
        <Link to="/help#sandbox" className="inline-flex min-h-9 items-center text-sm font-medium text-signal hover:underline">{t("common.sandbox_proof")}</Link>
      </PopoverContent>
    </Popover>
  );
}
