import * as AD from "@radix-ui/react-alert-dialog";
import type * as React from "react";
import { Button } from "./button";

interface ConfirmProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void;
  danger?: boolean;
  children?: React.ReactNode;
}

/** Confirmation for destructive actions. */
export function Confirm({ open, onOpenChange, title, body, confirmLabel, onConfirm, danger }: ConfirmProps) {
  return (
    <AD.Root open={open} onOpenChange={onOpenChange}>
      <AD.Portal>
        <AD.Overlay className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-[2px]" />
        <AD.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100vw-32px)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-panel)] border border-border bg-surface p-6 shadow-[var(--shadow-float)]">
          <AD.Title className="text-lg font-semibold">{title}</AD.Title>
          <AD.Description className="mt-2 text-sm text-muted">{body}</AD.Description>
          <div className="mt-6 flex justify-end gap-2">
            <AD.Cancel asChild>
              <Button variant="secondary">Cancel</Button>
            </AD.Cancel>
            <AD.Action asChild>
              <Button variant={danger ? "danger" : "primary"} onClick={onConfirm}>{confirmLabel}</Button>
            </AD.Action>
          </div>
        </AD.Content>
      </AD.Portal>
    </AD.Root>
  );
}
