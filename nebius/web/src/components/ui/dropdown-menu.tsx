import * as DM from "@radix-ui/react-dropdown-menu";
import * as React from "react";
import { cn } from "@/lib/utils";

export const DropdownMenu = DM.Root;
export const DropdownMenuTrigger = DM.Trigger;

export const DropdownMenuContent = React.forwardRef<
  React.ElementRef<typeof DM.Content>,
  React.ComponentPropsWithoutRef<typeof DM.Content>
>(({ className, sideOffset = 6, ...props }, ref) => (
  <DM.Portal>
    <DM.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn("z-50 min-w-44 rounded-[var(--radius-panel)] border border-border bg-surface p-1 shadow-[var(--shadow-float)]", className)}
      {...props}
    />
  </DM.Portal>
));
DropdownMenuContent.displayName = "DropdownMenuContent";

export const DropdownMenuItem = React.forwardRef<
  React.ElementRef<typeof DM.Item>,
  React.ComponentPropsWithoutRef<typeof DM.Item> & { danger?: boolean }
>(({ className, danger, ...props }, ref) => (
  <DM.Item
    ref={ref}
    className={cn(
      "flex cursor-default select-none items-center gap-2 rounded-[var(--radius-control)] px-2.5 py-1.5 text-sm outline-none",
      "data-[highlighted]:bg-surface-2 [&_svg]:size-4 [&_svg]:text-muted",
      danger && "text-danger [&_svg]:text-danger",
      className,
    )}
    {...props}
  />
));
DropdownMenuItem.displayName = "DropdownMenuItem";

export const DropdownMenuSeparator = () => <DM.Separator className="my-1 h-px bg-border" />;
export const DropdownMenuLabel = ({ children }: { children: React.ReactNode }) => (
  <DM.Label className="px-2.5 py-1 text-xs text-muted">{children}</DM.Label>
);
