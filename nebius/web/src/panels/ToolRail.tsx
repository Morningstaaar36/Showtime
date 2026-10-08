import { Ban, DoorOpen, Layers, Maximize, MousePointer2, Ruler, Spline, SquareDashed } from "lucide-react";
import type * as React from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Kbd } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { Tip } from "@/components/ui/tooltip";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { type Layers as L, type Mode, type Tool, useUi } from "@/state/ui";

const PLAN_TOOLS: { id: Tool; icon: React.ReactNode; key: string; kbd: string }[] = [
  { id: "select", icon: <MousePointer2 />, key: "tools.select", kbd: "V" },
  { id: "exit", icon: <DoorOpen />, key: "tools.exit", kbd: "E" },
  { id: "barrier", icon: <Spline />, key: "tools.barrier", kbd: "B" },
  { id: "zone", icon: <SquareDashed />, key: "tools.zone", kbd: "Z" },
  { id: "measure", icon: <Ruler />, key: "tools.measure", kbd: "M" },
];
const SIM_TOOLS: typeof PLAN_TOOLS = [
  { id: "select", icon: <MousePointer2 />, key: "tools.select", kbd: "V" },
  { id: "block", icon: <Ban />, key: "tools.block", kbd: "X" },
  { id: "measure", icon: <Ruler />, key: "tools.measure", kbd: "M" },
];

export function ToolRail({ mode, multiFloor, onResetView }: { mode: Mode; multiFloor: boolean; onResetView: () => void }) {
  const tool = useUi((s) => s.tool);
  const setTool = useUi((s) => s.setTool);
  const tools = mode === "plan" ? PLAN_TOOLS : mode === "simulate" ? SIM_TOOLS : SIM_TOOLS.slice(0, 1);
  return (
    <div className="pointer-events-auto flex flex-col gap-1 rounded-[10px] border border-border bg-surface/95 p-1 shadow-[var(--shadow-float)] backdrop-blur">
      {tools.map((x) => (
        <Tip key={x.id} side="right" content={<span>{t(x.key)} <Kbd>{x.kbd}</Kbd></span>}>
          <button type="button" aria-label={t(x.key)} aria-pressed={tool === x.id} onClick={() => setTool(x.id)}
                  className={cn("grid size-9 place-items-center rounded-[6px] transition [&_svg]:size-[18px]",
                    tool === x.id ? (x.id === "block" ? "bg-danger text-white" : "bg-signal text-signal-ink") : "text-muted hover:bg-surface-2 hover:text-ink")}>
            {x.icon}
          </button>
        </Tip>
      ))}
      <div className="mx-1.5 my-1 h-px bg-border" />
      <LayersPopover multiFloor={multiFloor} />
      <Tip side="right" content="Reset view">
        <button type="button" aria-label="Reset view" onClick={onResetView}
                className="grid size-9 place-items-center rounded-[6px] text-muted hover:bg-surface-2 hover:text-ink [&_svg]:size-[18px]">
          <Maximize />
        </button>
      </Tip>
    </div>
  );
}

function LayersPopover({ multiFloor }: { multiFloor: boolean }) {
  const layers = useUi((s) => s.layers);
  const toggle = useUi((s) => s.toggleLayer);
  const rows: [keyof L, string][] = [["people", "layers.people"], ["heatmap", "layers.heatmap"], ["terrain", "layers.terrain"],
    ["zones", "layers.zones"], ["labels", "layers.labels"], ["grid", "layers.grid"]];
  if (multiFloor) rows.push(["exploded", "layers.exploded"]);
  return (
    <Popover>
      <Tip side="right" content={t("layers.title")}>
        <PopoverTrigger asChild>
          <button type="button" aria-label={t("layers.title")} className="grid size-9 place-items-center rounded-[6px] text-muted hover:bg-surface-2 hover:text-ink [&_svg]:size-[18px]">
            <Layers />
          </button>
        </PopoverTrigger>
      </Tip>
      <PopoverContent side="right" align="start" className="w-60">
        <p className="mb-2 text-sm font-semibold">{t("layers.title")}</p>
        <ul className="space-y-2">
          {rows.map(([k, label]) => (
            <li key={k} className="flex items-center justify-between text-sm">
              <label htmlFor={`layer-${k}`}>{t(label)}</label>
              <Switch id={`layer-${k}`} checked={layers[k]} onCheckedChange={(v) => toggle(k, v)} />
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
