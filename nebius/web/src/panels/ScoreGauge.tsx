import { useEffect, useRef, useState } from "react";
import type { PlanScore } from "@/api/types";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { t } from "@/i18n";

const TONE: Record<string, string> = { A: "var(--egress)", B: "var(--egress)", C: "var(--caution)", D: "var(--caution)", F: "var(--danger)" };

/** Count up/down smoothly to a number (instant with reduced motion). */
export function useCountTo(target: number, ms = 700): number {
  const [v, setV] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { setV(target); from.current = target; return; }
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / ms);
      const e = 1 - Math.pow(1 - k, 3);
      setV(a + (target - a) * e);
      if (k < 1) raf = requestAnimationFrame(tick); else from.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

/** Animated ring with the planning score and grade; click for the breakdown. */
export function ScoreGauge({ score, size = 88, label = "Planning score", delta }: { score: PlanScore; size?: number; label?: string; delta?: number }) {
  const v = useCountTo(score.score);
  const r = size / 2 - 7;
  const c = 2 * Math.PI * r;
  const color = TONE[score.grade];
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className="group flex items-center gap-3 rounded-[var(--radius-panel)] text-left focus-visible:outline-2 focus-visible:outline-signal"
                aria-label={t("ui.scoregauge.aria", { label, grade: score.grade, score: score.score })}>
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0 -rotate-90">
            <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border)" strokeWidth={7} />
            <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={7} strokeLinecap="round"
                    strokeDasharray={c} strokeDashoffset={c * (1 - v / 100)} style={{ filter: `drop-shadow(0 0 6px ${color})` }} />
            <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" transform={`rotate(90 ${size / 2} ${size / 2})`}
                  className="fill-ink font-semibold" style={{ fontSize: size * 0.34 }}>{score.grade}</text>
          </svg>
          <span>
            <span className="block text-xs text-muted">{label}</span>
            <span className="block text-2xl font-semibold tabular leading-tight">{Math.round(v)}<span className="text-sm font-normal text-muted">/100</span></span>
            {delta !== undefined && delta !== 0 && (
              <span className={cn("block text-xs font-semibold tabular", delta > 0 ? "text-egress" : "text-danger")}>{t("ui.scoregauge.delta", { d: `${delta > 0 ? "+" : ""}${delta}` })}</span>
            )}
            <span className="block text-2xs text-muted group-hover:text-signal">{t("ui.scoregauge.how_is_this_computed")}</span>
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 text-sm">
        <p className="font-semibold">{label}: {score.grade} ({score.score}/100)</p>
        <p className="mt-0.5 text-xs text-muted">{t("ui.scoregauge.basis", { basis: score.basis })}</p>
        <ul className="mt-2 space-y-2">
          {score.parts.map((p) => (
            <li key={p.key}>
              <div className="flex justify-between text-xs"><span>{p.label} <span className="text-muted">× {p.weight}</span></span><span className="tabular font-semibold">{Math.round(p.score)}</span></div>
              <div className="mt-0.5 h-1 rounded-full bg-border"><div className="h-full rounded-full" style={{ width: `${p.score}%`, background: p.score >= 70 ? "var(--egress)" : p.score >= 40 ? "var(--caution)" : "var(--danger)" }} /></div>
              <p className="mt-0.5 text-2xs text-muted">{p.detail}</p>
            </li>
          ))}
        </ul>
        {score.capped && <p className="mt-2 text-xs font-medium text-danger">{score.capped}</p>}
      </PopoverContent>
    </Popover>
  );
}
