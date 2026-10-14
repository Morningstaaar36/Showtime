import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-[var(--radius-data)] px-1.5 py-0.5 text-xs font-medium tabular whitespace-nowrap [&_svg]:size-3",
  {
    variants: {
      // safety tones are darkened on the light theme so small text stays readable (≈5:1)
      tone: {
        neutral: "bg-surface-3 text-ink",
        outline: "border border-border text-muted",
        signal: "bg-signal-soft text-signal",
        egress: "bg-egress-soft text-[color-mix(in_srgb,var(--egress)_68%,black)] dark:text-egress",
        caution: "bg-caution-soft text-[color-mix(in_srgb,var(--caution)_62%,black)] dark:text-caution",
        danger: "bg-danger-soft text-[color-mix(in_srgb,var(--danger)_80%,black)] dark:text-danger",
        ink: "bg-ink text-plan",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({ className, tone, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
