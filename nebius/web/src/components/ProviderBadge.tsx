import { Cpu, Cloud } from "lucide-react";
import { useHealth } from "@/api/queries";
import { Tip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/** LOCAL / NEBIUS / cloud API badge with provider health in the tooltip. */
export function ProviderBadge() {
  const { data } = useHealth();
  const llm = data?.providers.llm;
  const cloud = llm?.provider === "nebius" || llm?.provider === "openai";
  const label = llm?.label ?? (cloud ? "CLOUD" : "LOCAL");
  const title =
    llm?.provider === "nebius" ? "Nebius Token Factory"
    : llm?.provider === "openai" ? `OpenAI-compatible API (${label})`
    : "Local model (llama.cpp)";
  const ok = llm?.ok ?? false;
  const fallback = !!(llm as { fallback?: boolean } | undefined)?.fallback;
  return (
    <Tip content={
      <div className="space-y-1">
        <p className="font-semibold">{title}</p>
        <p>{llm?.detail ?? "Checking…"}</p>
        <p>Sandbox: {data?.providers.sandbox.detail ?? "…"}</p>
      </div>
    }>
      <span className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-[var(--radius-control)] border px-2 text-2xs font-semibold tracking-wide",
        ok ? "border-border bg-surface text-ink" : "border-caution/40 bg-caution-soft text-ink",
      )}>
        {cloud ? <Cloud className="size-3.5" /> : <Cpu className="size-3.5" />}
        {label}{fallback && <span className="font-normal text-muted">→ LOCAL</span>}
        <span aria-hidden className={cn("size-1.5 rounded-full", ok && !fallback ? "bg-egress" : "bg-caution")} />
      </span>
    </Tip>
  );
}
