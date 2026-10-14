import { ChevronDown, Clapperboard, Eye, Sparkles, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { type Layers, useUi } from "@/state/ui";
import type { Tour } from "./Tour";

/** One "View" menu over the 3D scene: Showtime lights, the narrated tour and the layers. */
export function ViewMenu({ multiFloor, tour }: { multiFloor: boolean; tour: Tour }) {
  const layers = useUi((s) => s.layers);
  const toggle = useUi((s) => s.toggleLayer);
  const rows: [keyof Layers, string][] = [["people", "layers.people"], ["heatmap", "layers.heatmap"], ["terrain", "layers.terrain"],
    ["zones", "layers.zones"], ["labels", "layers.labels"], ["grid", "layers.grid"]];
  if (multiFloor) rows.push(["exploded", "layers.exploded"]);
  return (
    <div className="pointer-events-auto flex items-center gap-2">
      {tour.playing && (
        <Button size="sm" className="bg-surface/95 shadow-sm" onClick={tour.stop}><Square />{t("workspace.tour_stop_short")}</Button>
      )}
      <Popover>
        <PopoverTrigger asChild>
          <Button size="sm" className={cn("shadow-sm", layers.night ? "border-signal/50 bg-signal-soft" : "bg-surface/95")}>
            <Eye />{t("layers.title")}<ChevronDown className="text-muted" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-72 space-y-4">
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-3">
              <label htmlFor="view-night" className="flex items-center gap-2 font-medium"><Sparkles className="size-4 text-pink" aria-hidden />{t("workspace.view_lights")}</label>
              <Switch id="view-night" checked={layers.night} onCheckedChange={(v) => toggle("night", v)} />
            </div>
            <p className="text-xs text-muted">{t("workspace.view_lights_hint")}</p>
          </div>
          <Button className="w-full justify-start" onClick={() => (tour.playing ? tour.stop() : tour.play())}>
            {tour.playing ? <Square /> : <Clapperboard className="text-orange" />}{tour.playing ? t("workspace.tour_stop_short") : t("workspace.tour_play")}
          </Button>
          <div className="border-t border-border pt-3">
            <p className="mb-2 text-sm font-semibold">{t("workspace.view_layers")}</p>
            <ul className="space-y-2">
              {rows.map(([k, label]) => (
                <li key={k} className="flex items-center justify-between text-sm">
                  <label htmlFor={`layer-${k}`}>{t(label)}</label>
                  <Switch id={`layer-${k}`} checked={layers[k]} onCheckedChange={(v) => toggle(k, v)} />
                </li>
              ))}
            </ul>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
