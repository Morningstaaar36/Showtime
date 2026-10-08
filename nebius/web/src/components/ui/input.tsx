import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-9 w-full rounded-[var(--radius-control)] border border-border bg-surface px-3 text-sm text-ink tabular",
        "placeholder:text-muted/80 hover:border-border-strong focus-visible:border-signal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal/25",
        "disabled:opacity-60",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "w-full rounded-[var(--radius-control)] border border-border bg-surface px-3 py-2 text-sm text-ink",
        "placeholder:text-muted/80 focus-visible:border-signal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal/25",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-sm font-medium text-ink", className)} {...props} />;
}
