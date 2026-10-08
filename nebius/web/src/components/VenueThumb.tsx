import { useMemo } from "react";
import type { Pt, Venue } from "@/api/types";
import { bbox } from "@/scene/geom";
import { cn } from "@/lib/utils";

/** 2D plan drawing of a venue (SVG): outline, obstacles, zones, exits. Used in cards and pickers. */
export function VenueThumb({ venue, className, floor }: { venue: Venue; className?: string; floor?: string }) {
  const f = venue.floors.find((x) => x.floor_id === floor) ?? venue.floors[0];
  const all = venue.floors.flatMap((x) => x.walkable as Pt[]);
  const [x0, y0, x1, y1] = useMemo(() => bbox(all), [all]);
  const pad = Math.max(x1 - x0, y1 - y0) * 0.06;
  const vb = `${x0 - pad} ${-y1 - pad} ${x1 - x0 + 2 * pad} ${y1 - y0 + 2 * pad}`;
  const path = (pts: Pt[] | number[][]) => pts.map((p, i) => `${i ? "L" : "M"}${p[0]},${-p[1]}`).join(" ") + "Z";
  const sw = Math.max(x1 - x0, y1 - y0) / 220;
  return (
    <svg viewBox={vb} className={cn("block", className)} preserveAspectRatio="xMidYMid meet" aria-hidden>
      {venue.floors.filter((x) => x !== f).map((x) => (
        <path key={x.floor_id} d={path(x.walkable as Pt[])} className="fill-none stroke-line" strokeWidth={sw} strokeDasharray={`${sw * 4} ${sw * 3}`} />
      ))}
      <path d={path(f.walkable as Pt[])} className="fill-surface stroke-ink" strokeWidth={sw * 2.2} />
      {f.zones.map((z) => (
        <path key={z.id} d={path(z.polygon as Pt[])} className="fill-signal/10 stroke-signal/50" strokeWidth={sw} />
      ))}
      {f.obstacles.map((o) => (
        <path key={o.id} d={path(o.polygon as Pt[])}
              className={o.kind === "wall" ? "fill-ink stroke-none" : o.kind === "stage" ? "fill-line/70 stroke-ink" : "fill-line/40 stroke-line"}
              strokeWidth={sw} />
      ))}
      {f.exits.map((e) => (
        <path key={e.id} d={path(e.polygon as Pt[])} className={e.blocked ? "fill-danger stroke-danger" : "fill-egress stroke-egress"} strokeWidth={sw * 3} />
      ))}
    </svg>
  );
}
