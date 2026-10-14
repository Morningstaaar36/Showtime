import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-control)] font-medium " +
    "transition-colors disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0 " +
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal select-none",
  {
    variants: {
      variant: {
        primary: "bg-signal bg-[linear-gradient(135deg,var(--signal),color-mix(in_srgb,var(--signal)_70%,var(--pink)))] text-signal-ink shadow-[0_6px_16px_-6px_color-mix(in_srgb,var(--signal)_60%,transparent)] hover:brightness-110 active:brightness-95",
        secondary: "bg-surface text-ink border border-border hover:bg-surface-2 hover:border-border-strong",
        ghost: "text-ink hover:bg-surface-3/70",
        subtle: "bg-surface-2 text-ink hover:bg-surface-3",
        danger: "bg-danger text-white hover:brightness-110",
        "danger-ghost": "text-danger hover:bg-danger-soft",
        link: "text-signal underline-offset-4 hover:underline px-0 h-auto",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        md: "h-9 px-4 text-sm",
        lg: "h-12 px-6 text-base",
        icon: "size-9",
        "icon-sm": "size-8",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
  },
);
Button.displayName = "Button";
