/** A 3D replay on Your plan: one scene, or before and after side by side on one shared clock.
 * Overlays: the floor switcher, the caption of what happens now, who is in the crowd, the density
 * scale and what the numbers are based on. */
import type * as React from "react";
import type { Venue } from "@/api/types";
import { t } from "@/i18n";
import type { ObjectChange } from "@/lib/venueDiff";
import { cn } from "@/lib/utils";
import { FloorSwitch } from "@/panels/FloorSwitch";
import { DensityLegend, PeopleLegend } from "@/panels/Overlays";
import type { TimelineMarker } from "@/panels/Timeline";
import type { Replay } from "@/replay/useReplay";
import { SceneRoot } from "@/scene/SceneRoot";
import { ReplayCaption } from "./ScenarioViewer";
import { DensityScale } from "./visuals";

const noop = () => {};

function Scene({ venue, replay, clock, highlights }: { venue: Venue; replay: Replay | null; clock?: boolean; highlights?: ObjectChange[] }) {
  return (
    <SceneRoot venue={venue} replay={replay} hotspots={[]} marshals={[]} editable={false} resetNonce={0} quality="low" clock={clock}
               highlights={highlights} onExitClick={noop} onObjectClick={noop} onFloorClick={noop} onFloorDoubleClick={noop} onMove={noop} onHotspot={noop} />
  );
}

export interface StageSide { venue: Venue; replay: Replay | null }

export function ReplayStage({ label, main, compare, markers, basis, chip, top, corner, legend, highlights, className }: {
  label: string;
  main: StageSide;
  /** before, shown on the left of `main` (after), sharing its clock */
  compare?: StageSide | null;
  markers: TimelineMarker[];
  basis?: string;
  chip?: React.ReactNode;
  top?: React.ReactNode;
  corner?: React.ReactNode;
  /** the heatmap's scale; `title` and `max` for a layer in another unit (turbulence) */
  legend?: { warn: number; danger: number; title?: string; max?: number } | null;
  highlights?: ObjectChange[];
  className?: string;
}) {
  const split = !!compare;
  return (
    <section aria-label={label} className={cn("relative isolate overflow-hidden rounded-[var(--radius-panel)] border border-border bg-surface-2", className)}>
      {split ? (
        <div className="absolute inset-0 grid grid-cols-2 gap-0.5 bg-border-strong">
          <div className="relative min-w-0">
            <Scene venue={compare.venue} replay={compare.replay} clock={false} />
            <span className="pointer-events-none absolute bottom-3 left-3 z-40 rounded-full bg-ink px-3 py-1 text-xs font-semibold text-plan shadow-sm">{t("yourplan.before")}</span>
          </div>
          <div className="relative min-w-0">
            <Scene venue={main.venue} replay={main.replay} />
            <span className="pointer-events-none absolute bottom-3 left-3 z-40 rounded-full bg-signal px-3 py-1 text-xs font-semibold text-signal-ink shadow-sm">{t("yourplan.after")}</span>
          </div>
        </div>
      ) : (
        <div className="absolute inset-0"><Scene venue={main.venue} replay={main.replay} highlights={highlights} /></div>
      )}
      <FloorSwitch venue={main.venue} className="absolute right-3 top-3 z-50" />
      {chip && <div className="pointer-events-none absolute left-3 top-3 z-40 max-w-[60%]">{chip}</div>}
      {top && <div className="absolute inset-x-0 top-3 z-40 flex justify-center px-3 max-sm:top-14">{top}</div>}
      {main.replay && <ReplayCaption markers={markers} className="absolute inset-x-0 top-16 z-40 flex justify-center px-3 max-sm:top-28" />}
      <PeopleLegend replay={main.replay} className="absolute right-3 top-1/2 z-40 w-52 -translate-y-1/2 max-lg:hidden" />
      {legend && main.replay?.density && (
        <div className="pointer-events-none absolute bottom-14 right-3 z-40 max-md:hidden">
          {legend.title ? (
            <div className="w-56 rounded-[var(--radius-control)] border border-border bg-surface/90 px-3 py-2 shadow-sm backdrop-blur">
              <p className="mb-1.5 text-2xs font-medium text-muted">{legend.title}</p>
              <DensityScale value={null} warn={legend.warn} danger={legend.danger} max={legend.max} />
            </div>
          ) : <DensityLegend warn={legend.warn} danger={legend.danger} />}
        </div>
      )}
      {!split && basis && <span className="pointer-events-none absolute bottom-3 left-3 z-40 rounded-full bg-surface/95 px-3 py-1 text-xs shadow-sm">{basis}</span>}
      {corner && <div className="absolute bottom-3 right-3 z-40">{corner}</div>}
    </section>
  );
}
