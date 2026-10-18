/** Which floors the 3D view shows, as a lift panel: the storeys top to bottom (one in focus, the
 * others ghosted), the whole building, or the floors spread apart. Renders nothing for a
 * single-floor venue. */
import { Building2, Layers3, Users } from "lucide-react";
import type * as React from "react";
import type { Venue } from "@/api/types";
import { Tip } from "@/components/ui/tooltip";
import { t } from "@/i18n";
import { fmtInt } from "@/lib/format";
import { cn } from "@/lib/utils";
import { floorNamer } from "@/panels/FloorMenu";
import { floorsBottomUp, resolveFloorView } from "@/scene/geom";
import { useUi } from "@/state/ui";

export function FloorSwitch({ venue, className }: { venue: Venue; className?: string }) {
  const floorView = useUi((s) => s.floorView);
  const setFloorView = useUi((s) => s.setFloorView);
  if (venue.floors.length < 2) return null;
  const view = resolveFloorView(venue, floorView);
  const name = floorNamer(venue);
  const people = (id: string) => venue.floors.find((f) => f.floor_id === id)?.zones.reduce((n, z) => n + z.people, 0) ?? 0;
  const item = (id: string, label: string, icon?: React.ReactNode, tip?: string) => {
    const button = (
      <button key={id} type="button" role="radio" aria-checked={view === id} onClick={() => setFloorView(id)}
              className={cn("flex min-h-8 w-full items-center gap-1.5 whitespace-nowrap rounded-[6px] px-2 text-left text-xs font-medium transition-colors",
                            view === id ? "bg-signal text-signal-ink shadow-sm" : "text-muted hover:bg-surface-2 hover:text-ink")}>
        {icon}{label}
      </button>
    );
    return tip ? <Tip key={id} side="left" content={tip}>{button}</Tip> : button;
  };
  return (
    <div role="radiogroup" aria-label={t("floors.label")}
         className={cn("pointer-events-auto flex w-max max-w-[13rem] flex-col gap-0.5 rounded-[12px] border border-border bg-surface/95 p-1 shadow-[var(--shadow-float)] backdrop-blur", className)}>
      {item("all", t("floors.all"), <Building2 className="size-3.5 shrink-0" aria-hidden />)}
      {item("exploded", t("floors.exploded"), <Layers3 className="size-3.5 shrink-0" aria-hidden />)}
      <span aria-hidden className="mx-1 my-0.5 h-px bg-border" />
      {/* bottom-up in the DOM (keyboard order), top floor first on screen like a lift panel */}
      <div className="flex flex-col-reverse gap-0.5">
        {floorsBottomUp(venue).map((f) => (
          <div key={f.floor_id} className="flex items-center gap-1">
            <span className="min-w-0 flex-1">{item(f.floor_id, name(f.floor_id), undefined, t("floors.people_on", { n: fmtInt(people(f.floor_id)) }))}</span>
            <span aria-hidden className="flex w-9 shrink-0 items-center justify-end gap-0.5 pr-1 text-2xs text-muted tabular"><Users className="size-3" />{fmtInt(people(f.floor_id))}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
