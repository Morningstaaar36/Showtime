import { Ban, BrickWall, DoorClosed, DoorOpen, Footprints, LayoutPanelTop, Maximize, MousePointer2, Ruler, Spline, SquareDashed, TrendingUp } from "lucide-react";
import type * as React from "react";
import { Kbd } from "@/components/ui/misc";
import { Tip } from "@/components/ui/tooltip";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import type { ProjectDetail } from "@/api/types";
import { type Mode, type Tool, useUi } from "@/state/ui";
import { FloorPicker } from "./FloorMenu";

const PLAN_TOOLS: { id: Tool; icon: React.ReactNode; key: string; kbd: string }[] = [
  { id: "select", icon: <MousePointer2 />, key: "tools.select", kbd: "V" },
  { id: "exit", icon: <DoorOpen />, key: "tools.exit", kbd: "E" },
  { id: "barrier", icon: <Spline />, key: "tools.barrier", kbd: "B" },
  { id: "zone", icon: <SquareDashed />, key: "tools.zone", kbd: "Z" },
  { id: "measure", icon: <Ruler />, key: "tools.measure", kbd: "M" },
];
/** Building tools: they act on the floor chosen with the floor button below them. */
export const BUILD_RAIL: typeof PLAN_TOOLS = [
  { id: "wall", icon: <BrickWall />, key: "editor.tools.wall", kbd: "W" },
  { id: "door", icon: <DoorClosed />, key: "editor.tools.door", kbd: "D" },
  { id: "room", icon: <LayoutPanelTop />, key: "editor.tools.room", kbd: "O" },
  { id: "stair", icon: <TrendingUp />, key: "editor.tools.stair", kbd: "S" },
  { id: "route", icon: <Footprints />, key: "editor.tools.route", kbd: "P" },
];
const SIM_TOOLS: typeof PLAN_TOOLS = [
  { id: "select", icon: <MousePointer2 />, key: "tools.select", kbd: "V" },
  { id: "block", icon: <Ban />, key: "tools.block", kbd: "X" },
  { id: "measure", icon: <Ruler />, key: "tools.measure", kbd: "M" },
];

/** Editing tools on the left of the 3D view. Lights, tour and layers live in the View menu. */
export function ToolRail({ mode, onResetView, project }: { mode: Mode; onResetView: () => void; project?: ProjectDetail }) {
  const tool = useUi((s) => s.tool);
  const setTool = useUi((s) => s.setTool);
  const tools = mode === "plan" ? PLAN_TOOLS : mode === "simulate" ? SIM_TOOLS : SIM_TOOLS.slice(0, 1);
  const button = (x: (typeof PLAN_TOOLS)[number]) => (
    <Tip key={x.id} side="right" content={<span>{t(x.key)} <Kbd>{x.kbd}</Kbd></span>}>
      <button type="button" aria-label={t(x.key)} aria-pressed={tool === x.id} aria-keyshortcuts={x.kbd} onClick={() => setTool(x.id)}
              className={cn("grid size-10 place-items-center rounded-[var(--radius-control)] transition [&_svg]:size-[18px]",
                tool === x.id ? (x.id === "block" ? "bg-danger-soft text-danger ring-2 ring-danger/40" : "bg-signal text-signal-ink") : "text-muted hover:bg-surface-2 hover:text-ink")}>
        {x.icon}
      </button>
    </Tip>
  );
  return (
    <div className="pointer-events-auto flex flex-col gap-1 rounded-[var(--radius-panel)] border border-border bg-surface/95 p-1.5 shadow-[var(--shadow-float)] backdrop-blur">
      {tools.map(button)}
      {mode === "plan" && project && (
        <div role="group" aria-label={t("editor.tools.group")} className="flex flex-col gap-1">
          <div className="mx-1.5 my-1 h-px bg-border" />
          {BUILD_RAIL.map(button)}
          <FloorPicker project={project} />
        </div>
      )}
      <div className="mx-1.5 my-1 h-px bg-border" />
      <Tip side="right" content={t("workspace.reset_view")}>
        <button type="button" aria-label={t("workspace.reset_view")} onClick={onResetView}
                className="grid size-10 place-items-center rounded-[var(--radius-control)] text-muted hover:bg-surface-2 hover:text-ink [&_svg]:size-[18px]">
          <Maximize />
        </button>
      </Tip>
    </div>
  );
}
