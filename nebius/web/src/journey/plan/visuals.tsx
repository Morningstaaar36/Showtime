/** Small pictures for Your plan: the verdict ring, sparklines, bars against a target, the density
 * colour scale with its thresholds, and before → after deltas. Every picture has a text
 * equivalent (aria-label or visible numbers) so colour is never the only signal. */
import { ArrowDown, ArrowUp, Minus, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import { useId } from "react";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import type { VerdictLevel } from "@/panels/verdict";
import { CIVIDIS } from "@/scene/colormaps";

export const LEVEL_TONE: Record<VerdictLevel, { text: string; stroke: string; soft: string; ring: string }> = {
  holds: { text: "text-egress", stroke: "var(--egress)", soft: "bg-egress-soft", ring: "ring-egress/30" },
  at_risk: { text: "text-caution", stroke: "var(--caution)", soft: "bg-caution-soft", ring: "ring-caution/30" },
  fails: { text: "text-danger", stroke: "var(--danger)", soft: "bg-danger-soft", ring: "ring-danger/30" },
  unknown: { text: "text-muted", stroke: "var(--line)", soft: "bg-surface-2", ring: "ring-border" },
};

const SEGMENTS: VerdictLevel[] = ["fails", "at_risk", "holds"];

/** Traffic-light ring: three arcs (fails, at risk, holds); the plan's own one lit, a shield in
 * the middle. The word next to it carries the meaning; the ring repeats it. */
export function VerdictRing({ level, size = 132, className }: { level: VerdictLevel; size?: number; className?: string }) {
  const r = size / 2 - 10;
  const c = 2 * Math.PI * r;
  const gap = 0.025 * c;
  const seg = c / 3 - gap;
  const Icon = level === "holds" ? ShieldCheck : level === "fails" ? ShieldAlert : ShieldQuestion;
  return (
    <div className={cn("relative shrink-0", className)} style={{ width: size, height: size }} aria-hidden>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-[210deg]">
        {SEGMENTS.map((s, i) => (
          <circle key={s} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={LEVEL_TONE[s].stroke} strokeWidth={s === level ? 12 : 7}
                  strokeLinecap="round" strokeDasharray={`${seg} ${c - seg}`} strokeDashoffset={-i * (seg + gap)}
                  opacity={s === level ? 1 : 0.18} className={s === level ? "animate-ring-in" : undefined} />
        ))}
      </svg>
      <span className={cn("absolute inset-0 grid place-items-center", LEVEL_TONE[level].text)}>
        <span className={cn("grid place-items-center rounded-full", LEVEL_TONE[level].soft)} style={{ width: size * 0.5, height: size * 0.5 }}>
          <Icon style={{ width: size * 0.28, height: size * 0.28 }} strokeWidth={2.2} />
        </span>
      </span>
    </div>
  );
}

/** A tiny line over time; `marks` draws horizontal reference lines (thresholds). */
export function Sparkline({ values, max, tone = "var(--signal)", marks = [], label, className, area = true }: {
  values: number[]; max?: number; tone?: string; marks?: { v: number; tone: string }[]; label: string; className?: string; area?: boolean;
}) {
  const id = useId();
  if (values.length < 2) return null;
  const W = 120, H = 32;
  const top = Math.max(max ?? 0, ...values, ...marks.map((m) => m.v), 1e-6);
  const pts = values.map((v, i) => [(i / (values.length - 1)) * W, H - 2 - (v / top) * (H - 4)] as const);
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label} className={cn("h-8 w-full overflow-visible", className)}>
      <defs>
        <linearGradient id={`g${id}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={tone} stopOpacity="0.28" />
          <stop offset="1" stopColor={tone} stopOpacity="0" />
        </linearGradient>
      </defs>
      {marks.map((m) => (
        <line key={m.v} x1={0} x2={W} y1={H - 2 - (m.v / top) * (H - 4)} y2={H - 2 - (m.v / top) * (H - 4)} stroke={m.tone}
              strokeWidth={1} strokeDasharray="3 2" vectorEffect="non-scaling-stroke" />
      ))}
      {area && <path d={`${d}L${W},${H}L0,${H}Z`} fill={`url(#g${id})`} />}
      <path d={d} fill="none" stroke={tone} strokeWidth={1.75} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}

/** A value against a target: the bar fills up to the value, the target is a notch with its label. */
export function TargetBar({ value, target, targetLabel, over }: { value: number | null; target: number; targetLabel: string; over: boolean }) {
  const top = Math.max(target * 1.5, value ?? 0);
  const pct = value == null ? 100 : Math.min(100, (value / top) * 100);
  const at = (target / top) * 100;
  return (
    <div className="space-y-1">
      <div className="relative h-2.5 rounded-full bg-surface-3">
        <div className={cn("h-full rounded-full transition-[width] duration-700", value == null ? "bg-[repeating-linear-gradient(45deg,var(--danger)_0_6px,transparent_6px_10px)]" : over ? "bg-danger" : "bg-egress")}
             style={{ width: `${pct}%` }} />
        <span className="absolute -top-1 h-4.5 w-0.5 rounded-full bg-ink" style={{ left: `${at}%` }} />
      </div>
      <p className="relative h-4 text-2xs text-muted tabular"><span className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${Math.min(88, Math.max(12, at))}%` }}>{targetLabel}</span></p>
    </div>
  );
}

const CIVIDIS_STOPS = Array.from({ length: 12 }, (_, i) => {
  const k = Math.round((i / 11) * 255);
  return `rgb(${CIVIDIS[k * 3]},${CIVIDIS[k * 3 + 1]},${CIVIDIS[k * 3 + 2]}) ${(i / 11) * 100}%`;
}).join(",");

/** Density on the heatmap's own colour scale, with the warning and danger thresholds marked. */
export function DensityScale({ value, warn, danger, max = 7 }: { value: number | null; warn: number; danger: number; max?: number }) {
  const pos = (v: number) => `${Math.min(100, (v / max) * 100)}%`;
  return (
    <div className="space-y-1" aria-hidden>
      <div className="relative h-2.5 rounded-full" style={{ background: `linear-gradient(90deg,${CIVIDIS_STOPS})` }}>
        <span className="absolute -top-1 h-4.5 w-0.5 bg-caution" style={{ left: pos(warn) }} />
        <span className="absolute -top-1 h-4.5 w-0.5 bg-danger" style={{ left: pos(danger) }} />
        {value != null && (
          <span className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-surface bg-ink shadow-md transition-[left] duration-700"
                style={{ left: pos(value) }} />
        )}
      </div>
      <p className="relative h-4 text-2xs font-semibold tabular">
        <span className="absolute -translate-x-1/2 text-[color-mix(in_srgb,var(--caution)_62%,black)] dark:text-caution" style={{ left: pos(warn) }}>{warn}</span>
        <span className="absolute -translate-x-1/2 text-[color-mix(in_srgb,var(--danger)_80%,black)] dark:text-danger" style={{ left: pos(danger) }}>{danger}</span>
      </p>
    </div>
  );
}

/** "−42%" with an arrow: green when the change is an improvement, red when it is worse. */
export function DeltaChip({ before, after, lowerBetter = true }: { before: number | null; after: number | null; lowerBetter?: boolean }) {
  if (before == null || after == null) return null;
  const diff = after - before;
  const same = Math.abs(diff) < 1e-9 || (before !== 0 && Math.abs(diff / before) < 0.005);
  const better = lowerBetter ? diff < 0 : diff > 0;
  const pct = before !== 0 ? Math.round((diff / Math.abs(before)) * 100) : null;
  const Icon = same ? Minus : diff < 0 ? ArrowDown : ArrowUp;
  return (
    <span className={cn("inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-xs font-semibold tabular",
                        same ? "bg-surface-3 text-muted" : better ? "bg-egress-soft text-[color-mix(in_srgb,var(--egress)_68%,black)] dark:text-egress"
                          : "bg-danger-soft text-[color-mix(in_srgb,var(--danger)_80%,black)] dark:text-danger")}>
      <Icon className="size-3" aria-hidden />
      {same ? t("plan.same") : pct != null ? `${pct > 0 ? "+" : ""}${pct}%` : t(better ? "plan.better" : "plan.worse")}
    </span>
  );
}
