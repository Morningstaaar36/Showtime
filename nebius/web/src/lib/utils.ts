import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind class names (shadcn/ui convention). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Clamp a number. */
export function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

/** Short random id for client-side objects (exits, barriers). */
export function shortId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 7)}`;
}

/** One toast slot for "saved, Undo": the server undoes only the latest edit, so a newer save
 *  replaces the older toast instead of leaving an Undo button that would undo the wrong change. */
export const UNDO_TOAST_ID = "undo-latest-edit";
