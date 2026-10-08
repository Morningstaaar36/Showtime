import * as ScrollAreaPrimitive from "@radix-ui/react-scroll-area";
import * as ProgressPrimitive from "@radix-ui/react-progress";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export function Separator({ className, vertical }: { className?: string; vertical?: boolean }) {
  return <div role="separator" className={cn(vertical ? "w-px self-stretch" : "h-px w-full", "bg-border", className)} />;
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex min-w-5 items-center justify-center rounded-[4px] border border-border bg-surface-2 px-1.5 text-2xs font-medium text-muted">
      {children}
    </kbd>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 aria-hidden className={cn("size-4 animate-spin text-muted", className)} />;
}

export const ScrollArea = React.forwardRef<
  React.ElementRef<typeof ScrollAreaPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ScrollAreaPrimitive.Root>
>(({ className, children, ...props }, ref) => (
  <ScrollAreaPrimitive.Root ref={ref} className={cn("relative overflow-hidden", className)} {...props}>
    <ScrollAreaPrimitive.Viewport className="size-full rounded-[inherit]">{children}</ScrollAreaPrimitive.Viewport>
    <ScrollAreaPrimitive.Scrollbar orientation="vertical" className="flex w-2 touch-none select-none p-0.5">
      <ScrollAreaPrimitive.Thumb className="relative flex-1 rounded-full bg-border-strong" />
    </ScrollAreaPrimitive.Scrollbar>
  </ScrollAreaPrimitive.Root>
));
ScrollArea.displayName = "ScrollArea";

export function Progress({ value, className, tone = "signal" }: { value: number; className?: string; tone?: "signal" | "egress" | "danger" }) {
  const bar = tone === "egress" ? "bg-egress" : tone === "danger" ? "bg-danger" : "bg-signal";
  return (
    <ProgressPrimitive.Root className={cn("relative h-1.5 w-full overflow-hidden rounded-full bg-surface-3", className)} value={value}>
      <ProgressPrimitive.Indicator className={cn("h-full transition-[width] duration-500", bar)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </ProgressPrimitive.Root>
  );
}

/** Skeleton block for loading states. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-[var(--radius-control)] bg-surface-3", className)} />;
}

/** Section header used in panels (sentence case, no all-caps labels). */
export function PanelTitle({ children, action, className }: { children: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-center justify-between gap-2", className)}>
      <h3 className="text-sm font-semibold text-ink">{children}</h3>
      {action}
    </div>
  );
}
