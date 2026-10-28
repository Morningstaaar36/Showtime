import { Navigation } from "lucide-react";
import { CIVIDIS } from "@/scene/colormaps";
import { DENSITY_MAX } from "@/replay/density";
import { t } from "@/i18n";
import { fmtInt } from "@/lib/format";
import { cn } from "@/lib/utils";
import { kindsPresent, PEOPLE_KINDS, type PeopleKindId } from "@/replay/kinds";
import type { Replay } from "@/replay/useReplay";
import { PEOPLE_LOOK } from "@/scene/peopleLook";

/** North arrow + scale bar, like a plan drawing. */
export function PlanCompass({ span }: { span: number }) {
  const nice = [5, 10, 20, 25, 50, 100].find((n) => n >= span / 8) ?? 100;
  return (
    <div className="pointer-events-none flex items-end gap-3 rounded-[var(--radius-control)] border border-border bg-surface/90 px-3 py-2 text-2xs text-muted shadow-sm backdrop-blur">
      <div className="flex flex-col items-center"><Navigation className="size-4 rotate-0 text-ink" fill="currentColor" /><span className="font-semibold text-ink">{t("ui.overlays.north")}</span></div>
      <div>
        <div className="flex h-1.5 w-20 overflow-hidden rounded-[1px] border border-ink"><span className="w-1/2 bg-ink" /><span className="w-1/2" /></div>
        <div className="mt-0.5 flex w-20 justify-between tabular"><span>0</span><span>{t("units.n_m", { n: nice })}</span></div>
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
    <div className="pointer-events-none w-64 rounded-[var(--radius-control)] border border-border bg-surface/90 px-3 py-2 shadow-sm backdrop-blur">
      <p className="text-2xs font-medium text-muted">{t("ui.overlays.people_per_m")}</p>
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
        <span className="flex items-center gap-1"><span className="h-2 w-0.5 bg-caution" />{t("ui.overlays.warning")}</span>
        <span className="flex items-center gap-1"><span className="h-2 w-0.5 bg-danger" />{t("ui.overlays.danger_outlined_in_3d")}</span>
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

/** Who is in the replay: each kind's marker shape and colour, with how many people. Renders nothing
 * when everyone is a general adult. */
export function PeopleLegend({ replay, className }: { replay: Replay | null | undefined; className?: string }) {
  const present = kindsPresent(replay?.kinds ?? null);
  if (!replay?.kinds || present.length < 2) return null;
  const total = replay.traj.index.max_agents;
  const listed = PEOPLE_KINDS.reduce((n, k) => n + (k === "general" ? 0 : replay.kinds!.listed[k]), 0);
  const count = (k: PeopleKindId) => (k === "general" ? Math.max(0, total - listed) : replay.kinds!.listed[k]);
  const shown = present.filter((k) => count(k) > 0); // a school of children and staff has no "general adults" row
  return (
    <section aria-label={t("replay.people_legend")}
             className={cn("pointer-events-none rounded-[var(--radius-control)] border border-border bg-surface/90 px-3 py-2 shadow-sm backdrop-blur", className)}>
      <p className="text-2xs font-medium text-muted">{t("replay.people_legend")}</p>
      <ul className="mt-1 grid gap-0.5">
        {shown.map((k) => (
          <li key={k} className="flex items-center gap-2 text-xs">
            <svg viewBox="0 0 16 16" className="size-3.5 shrink-0" aria-hidden>
              <path d={PEOPLE_LOOK[k].icon} fillRule="evenodd" fill={PEOPLE_LOOK[k].color ?? "currentColor"} stroke="var(--ink)" strokeWidth={0.6} />
            </svg>
            <span className="flex-1">{t(`editor.people.${k}`)}</span>
            <span className="tabular text-muted">{fmtInt(count(k))}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
