/** Which floors the 3D view shows: all stacked, spread apart, or one floor alone. Renders nothing
 * for a single-floor venue. */
import { Layers3 } from "lucide-react";
import type { Venue } from "@/api/types";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { floorsBottomUp, resolveFloorView } from "@/scene/geom";
import { useUi } from "@/state/ui";

export function FloorSwitch({ venue, className }: { venue: Venue; className?: string }) {
  const floorView = useUi((s) => s.floorView);
  const setFloorView = useUi((s) => s.setFloorView);
  if (venue.floors.length < 2) return null;
  const view = resolveFloorView(venue, floorView);
  const options: [string, string][] = [
    ["all", t("floors.all")],
    ["exploded", t("floors.exploded")],
    ...floorsBottomUp(venue).map((f): [string, string] => [f.floor_id, f.name || f.floor_id]),
  ];
  return (
    <div role="radiogroup" aria-label={t("floors.label")}
         className={cn("pointer-events-auto flex max-w-full items-center gap-0.5 overflow-x-auto rounded-[var(--radius-control)] border border-border bg-surface/95 p-0.5 shadow-sm", className)}>
      <Layers3 className="mx-1 size-4 shrink-0 text-muted" aria-hidden />
      {options.map(([id, label]) => (
        <button key={id} type="button" role="radio" aria-checked={view === id} onClick={() => setFloorView(id)}
                className={cn("shrink-0 whitespace-nowrap rounded-[4px] px-2 py-1 text-xs",
                              view === id ? "bg-signal text-white" : "text-muted hover:text-ink")}>
          {label}
        </button>
      ))}
    </div>
  );
}
