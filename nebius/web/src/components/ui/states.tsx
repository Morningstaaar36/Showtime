import { AlertTriangle, WifiOff } from "lucide-react";
import type * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

/** Designed empty state: what is missing and the next action. */
export function EmptyState({ icon, title, body, children, className }: {
  icon?: React.ReactNode; title: string; body?: string; children?: React.ReactNode; className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-start gap-3 rounded-[var(--radius-panel)] border border-dashed border-border-strong bg-surface/60 p-6", className)}>
      {icon && <div className="text-line [&_svg]:size-6">{icon}</div>}
      <div>
        <p className="font-semibold text-ink">{title}</p>
        {body && <p className="mt-1 max-w-prose text-sm text-muted">{body}</p>}
      </div>
      {children && <div className="flex flex-wrap gap-2">{children}</div>}
    </div>
  );
}

/** Designed error state: what happened and how to fix it (no apologies). */
export function ErrorState({ title, message, hint, onRetry, className }: {
  title?: string; message: string; hint?: string | null; onRetry?: () => void; className?: string;
}) {
  const offline = message.includes("isn't reachable");
  return (
    <div role="alert" className={cn("flex items-start gap-3 rounded-[var(--radius-panel)] border border-danger/30 bg-danger-soft p-4", className)}>
      {offline ? <WifiOff className="mt-0.5 size-5 shrink-0 text-danger" /> : <AlertTriangle className="mt-0.5 size-5 shrink-0 text-danger" />}
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold text-ink">{title}</p>}
        <p className="text-sm text-ink">{message}</p>
        {hint && <p className="mt-1 text-sm text-muted">{hint}</p>}
      </div>
      {onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

/** Thin banner at the top of a screen for degraded modes. */
export function Banner({ tone = "caution", icon, children }: { tone?: "caution" | "signal" | "danger"; icon?: React.ReactNode; children: React.ReactNode }) {
  const cls = tone === "danger" ? "bg-danger-soft text-ink border-danger/30"
    : tone === "signal" ? "bg-signal-soft text-ink border-signal/30" : "bg-caution-soft text-ink border-caution/30";
  return (
    <div role="status" className={cn("flex items-center gap-2 border-b px-4 py-1.5 text-sm [&_svg]:size-4", cls)}>
      {icon}
      <span className="min-w-0 truncate">{children}</span>
    </div>
  );
}
