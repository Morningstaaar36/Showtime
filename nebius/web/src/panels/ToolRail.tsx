import { Ban, DoorOpen, Maximize, MousePointer2, Ruler, Spline, SquareDashed } from "lucide-react";
import type * as React from "react";
import { Kbd } from "@/components/ui/misc";
import { Tip } from "@/components/ui/tooltip";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { type Mode, type Tool, useUi } from "@/state/ui";

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

/** Editing tools on the left of the 3D view. Lights, tour and layers live in the View menu. */
export function ToolRail({ mode, onResetView }: { mode: Mode; onResetView: () => void }) {
  const tool = useUi((s) => s.tool);
  const setTool = useUi((s) => s.setTool);
  const tools = mode === "plan" ? PLAN_TOOLS : mode === "simulate" ? SIM_TOOLS : SIM_TOOLS.slice(0, 1);
  return (
    <div className="pointer-events-auto flex flex-col gap-1 rounded-[var(--radius-panel)] border border-border bg-surface/95 p-1.5 shadow-[var(--shadow-float)] backdrop-blur">
      {tools.map((x) => (
        <Tip key={x.id} side="right" content={<span>{t(x.key)} <Kbd>{x.kbd}</Kbd></span>}>
          <button type="button" aria-label={t(x.key)} aria-pressed={tool === x.id} onClick={() => setTool(x.id)}
                  className={cn("grid size-10 place-items-center rounded-[var(--radius-control)] transition [&_svg]:size-[18px]",
                    tool === x.id ? (x.id === "block" ? "bg-danger-soft text-danger ring-2 ring-danger/40" : "bg-signal text-signal-ink") : "text-muted hover:bg-surface-2 hover:text-ink")}>
            {x.icon}
          </button>
        </Tip>
      ))}
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
