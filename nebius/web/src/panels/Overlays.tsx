import { Navigation } from "lucide-react";
import { CIVIDIS } from "@/scene/colormaps";
import { DENSITY_MAX } from "@/scene/ReplayLayers";
import { cn } from "@/lib/utils";

/** North arrow + scale bar, like a plan drawing. */
export function PlanCompass({ span }: { span: number }) {
  const nice = [5, 10, 20, 25, 50, 100].find((n) => n >= span / 8) ?? 100;
  return (
    <div className="pointer-events-none flex items-end gap-3 rounded-[8px] border border-border bg-surface/90 px-3 py-2 text-2xs text-muted shadow-sm backdrop-blur">
      <div className="flex flex-col items-center"><Navigation className="size-4 rotate-0 text-ink" fill="currentColor" /><span className="font-semibold text-ink">N</span></div>
      <div>
        <div className="flex h-1.5 w-20 overflow-hidden rounded-[1px] border border-ink"><span className="w-1/2 bg-ink" /><span className="w-1/2" /></div>
        <div className="mt-0.5 flex w-20 justify-between tabular"><span>0</span><span>{nice} m</span></div>
      </div>
    </div>
  );
}

/** Colour scale for the density heatmap; thresholds are marked (colour is never the only signal). */
export function DensityLegend({ warn, danger }: { warn: number; danger: number }) {
  const stops = Array.from({ length: 12 }, (_, i) => {
    const k = Math.round((i / 11) * 255);
    return `rgb(${CIVIDIS[k * 3]},${CIVIDIS[k * 3 + 1]},${CIVIDIS[k * 3 + 2]}) ${(i / 11) * 100}%`;
  }).join(",");
  const pos = (v: number) => `${(v / DENSITY_MAX) * 100}%`;
  return (
    <div className="pointer-events-none w-64 rounded-[8px] border border-border bg-surface/90 px-3 py-2 shadow-sm backdrop-blur">
      <p className="text-2xs font-medium text-muted">People per m²</p>
      <div className="relative mt-1.5 h-2.5 rounded-[2px]" style={{ background: `linear-gradient(90deg,${stops})` }}>
        <span className="absolute -top-1 h-4.5 w-0.5 bg-caution" style={{ left: pos(warn) }} />
        <span className="absolute -top-1 h-4.5 w-0.5 bg-danger" style={{ left: pos(danger) }} />
      </div>
      <div className="relative mt-1 h-3.5 text-2xs tabular text-muted">
        <span className="absolute left-0">0</span>
        <span className="absolute -translate-x-1/2 font-semibold text-caution" style={{ left: pos(warn) }}>{warn}</span>
        <span className="absolute -translate-x-1/2 font-semibold text-danger" style={{ left: pos(danger) }}>{danger}</span>
        <span className="absolute right-0">{DENSITY_MAX}+</span>
      </div>
      <div className="mt-1 flex gap-3 text-2xs text-muted">
        <span className="flex items-center gap-1"><span className="h-2 w-0.5 bg-caution" />warning</span>
        <span className="flex items-center gap-1"><span className="h-2 w-0.5 bg-danger" />danger (outlined in 3D)</span>
      </div>
    </div>
  );
}

export function TierChip({ label, tone }: { label: string; tone: "estimate" | "confirmed" | "partial" }) {
  return (
    <span className={cn("pointer-events-auto inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium shadow-sm backdrop-blur",
      tone === "confirmed" ? "border-egress/40 bg-surface/95 text-ink" : "border-border bg-surface/95 text-ink")}>
      <span className={cn("size-1.5 rounded-full", tone === "confirmed" ? "bg-egress" : tone === "partial" ? "bg-caution" : "bg-line")} />
      {label}
    </span>
  );
}
