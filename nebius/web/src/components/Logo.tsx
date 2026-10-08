import { cn } from "@/lib/utils";

/** Wordmark: a plan-drawing frame with a green exit. */
export function Logo({ className, compact }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight text-ink", className)}>
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
        <rect width="32" height="32" rx="7" className="fill-ink" />
        <path d="M7 23V9h6l3 5 3-5h6v14" fill="none" className="stroke-plan" strokeWidth="2.2" strokeLinejoin="round" />
        <rect x="13" y="19" width="6" height="4" className="fill-egress" />
      </svg>
      {!compact && <span className="text-[17px]">Showtime</span>}
    </span>
  );
}
