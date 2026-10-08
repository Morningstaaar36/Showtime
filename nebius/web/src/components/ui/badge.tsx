import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-[var(--radius-data)] px-1.5 py-0.5 text-xs font-medium tabular whitespace-nowrap [&_svg]:size-3",
  {
    variants: {
      tone: {
        neutral: "bg-surface-3 text-ink",
        outline: "border border-border text-muted",
        signal: "bg-signal-soft text-signal",
        egress: "bg-egress-soft text-egress",
        caution: "bg-caution-soft text-caution",
        danger: "bg-danger-soft text-danger",
        ink: "bg-ink text-plan",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({ className, tone, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
