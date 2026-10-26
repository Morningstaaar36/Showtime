/** The palette over the 3D view: drag a door, fence, crowd area or stall onto the venue (or click
 * one, then click the venue). Also finishes drags of objects grabbed in 3D. */
import { DoorOpen, Fence, Store, Users } from "lucide-react";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { CROWD_PEOPLE, DOOR_WIDTH, type Hit, type PaletteItem } from "./dragDrop";
import { type Grab, useDrag } from "./dragStore";

export const PALETTE: { item: PaletteItem; icon: React.ReactNode; tone: string }[] = [
  { item: "door", icon: <DoorOpen />, tone: "bg-emerald-500" },
  { item: "fence", icon: <Fence />, tone: "bg-amber-500" },
  { item: "crowd", icon: <Users />, tone: "bg-sky-500" },
  { item: "stall", icon: <Store />, tone: "bg-fuchsia-500" },
];
const CLICK_PX = 6;

export function DropPalette({ disabled, onPlace, onMove }: {
  disabled: boolean;
  onPlace: (item: PaletteItem, hit: Hit) => void;
  onMove: (grab: Grab, hit: Hit) => void;
}) {
  const item = useDrag((s) => s.item);
  const armed = useDrag((s) => s.armed);
  const grab = useDrag((s) => s.grab);
  const pointer = useDrag((s) => s.pointer);
  const hit = useDrag((s) => s.hit);
  const down = useRef<[number, number] | null>(null);
  const busy = !!(item || armed || grab);

  useEffect(() => {
    if (!busy) return;
    const move = (e: PointerEvent) => {
      const s = useDrag.getState();
      const at: [number, number] = [e.clientX, e.clientY];
      const h = s.pick?.(e.clientX, e.clientY, s.grab?.floorId) ?? null;
      if (s.grab && !s.grab.active && Math.hypot(at[0] - s.grab.client[0], at[1] - s.grab.client[1]) > CLICK_PX) {
        s.set({ grab: { ...s.grab, active: true }, pointer: at, hit: h });
      } else s.set({ pointer: at, hit: h });
    };
    const up = (e: PointerEvent) => {
      const s = useDrag.getState();
      const h = s.pick?.(e.clientX, e.clientY, s.grab?.floorId) ?? null;
      if (s.item) {
        const start = down.current;
        const clicked = start && Math.hypot(e.clientX - start[0], e.clientY - start[1]) <= CLICK_PX;
        if (clicked) { s.set({ item: null, armed: s.item, pointer: null }); return; }
        const it = s.item;
        s.reset();
        if (h?.inside) onPlace(it, h);
        else toast.message(t("check.drop_on_venue"));
        return;
      }
      if (s.grab) {
        const g = s.grab;
        s.reset();
        if (!g.active) return;
        if (g.locked) { toast.message(t("check.unlock_first")); return; }
        if (h) onMove(g, h);
      }
    };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") useDrag.getState().reset(); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("keydown", key);
    };
  }, [busy, onPlace, onMove]);

  const dragging = item ? PALETTE.find((p) => p.item === item) : null;
  return (
    <>
      <div role="toolbar" aria-label={t("check.palette")}
           className="pointer-events-auto flex gap-1.5 rounded-[14px] border border-border bg-surface/95 p-1.5 shadow-[var(--shadow-float)]">
        {PALETTE.map((p) => (
          <button key={p.item} type="button" disabled={disabled} aria-pressed={armed === p.item}
                  title={t(`check.palette_${p.item}_hint`, { w: DOOR_WIDTH, n: CROWD_PEOPLE })}
                  onPointerDown={(e) => {
                    if (disabled || e.button !== 0) return;
                    e.preventDefault();
                    down.current = [e.clientX, e.clientY];
                    useDrag.getState().set({ item: p.item, armed: null, grab: null, pointer: [e.clientX, e.clientY], hit: null });
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); useDrag.getState().set({ armed: p.item }); }
                  }}
                  className={cn("flex min-h-11 touch-none select-none items-center gap-2 rounded-[10px] px-2.5 py-1.5 text-sm font-semibold transition hover:bg-surface-2 disabled:opacity-40",
                    armed === p.item && "bg-signal-soft ring-2 ring-signal")}>
            <span className={cn("grid size-8 place-items-center rounded-full text-white shadow-sm [&_svg]:size-[18px]", p.tone)}>{p.icon}</span>
            <span className="hidden sm:inline">{t(`check.palette_${p.item}`)}</span>
          </button>
        ))}
      </div>
      {dragging && pointer && (
        <div className="pointer-events-none fixed z-50 -translate-x-1/2 -translate-y-[calc(100%+12px)]" style={{ left: pointer[0], top: pointer[1] }}>
          <div className="flex items-center gap-2 rounded-full bg-ink/90 py-1 pl-1 pr-3 text-sm font-medium text-plan shadow-lg">
            <span className={cn("grid size-7 place-items-center rounded-full text-white [&_svg]:size-4", dragging.tone)}>{dragging.icon}</span>
            {hit?.inside ? t(dragging.item === "door" ? "check.release_door" : "check.release_here") : t("check.drop_on_venue")}
          </div>
        </div>
      )}
    </>
  );
}
