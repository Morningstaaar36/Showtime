import { Pause, Play, SkipBack } from "lucide-react";
import { useEffect, useState } from "react";
import { Slider } from "@/components/ui/slider";
import { Tip } from "@/components/ui/tooltip";
import { t } from "@/i18n";
import { isTypingTarget } from "@/lib/keyboard";
import { fmtClock } from "@/lib/format";
import { cn } from "@/lib/utils";
import { usePlayback } from "@/state/playback";

export interface TimelineMarker {
  t: number;
  label: string;
  tone: "danger" | "caution" | "signal" | "egress";
}

/** Replay controls. The clock itself ticks inside the 3D scene; this reads it ~10×/s. */
export function Timeline({ markers }: { markers: TimelineMarker[] }) {
  const duration = usePlayback((s) => s.duration);
  const playing = usePlayback((s) => s.playing);
  const speed = usePlayback((s) => s.speed);
  const [now, setNow] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setNow(usePlayback.getState().t), 100);
    return () => window.clearInterval(id);
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (e.code === "Space" && tag !== "BUTTON" && !isTypingTarget(e.target)) {
        e.preventDefault();
        usePlayback.getState().toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const pb = usePlayback.getState();
  return (
    <div className="pointer-events-auto flex min-w-0 items-center gap-2 rounded-[var(--radius-panel)] sm:gap-3 border border-border bg-surface/95 px-3 py-2 shadow-[var(--shadow-float)] backdrop-blur">
      <Tip content="Back to start">
        <button type="button" aria-label="Back to start" onClick={() => pb.setT(0)} className="text-muted hover:text-ink"><SkipBack className="size-4" /></button>
      </Tip>
      <button type="button" aria-label={playing ? t("timeline.pause") : t("timeline.play")} onClick={() => pb.toggle()}
              className="grid size-9 place-items-center rounded-full bg-ink text-plan transition hover:scale-105">
        {playing ? <Pause className="size-4" fill="currentColor" /> : <Play className="ml-0.5 size-4" fill="currentColor" />}
      </button>
      <div className="flex rounded-[var(--radius-control)] bg-surface-2 p-0.5 text-xs">
        {[1, 4, 16].map((s) => (
          <button key={s} type="button" onClick={() => pb.setSpeed(s)} aria-pressed={speed === s}
                  className={cn("rounded-[4px] px-2 py-0.5 font-medium tabular", speed === s ? "bg-surface shadow-sm" : "text-muted")}>
            {s}×
          </button>
        ))}
      </div>
      <div className="relative min-w-0 flex-1">
        <Slider value={[now]} min={0} max={Math.max(duration, 1)} step={0.25} thumbLabel="Replay time"
                onValueChange={(v) => { pb.setT(v[0]); }} />
        <div className="pointer-events-none absolute inset-x-0 -top-2.5 h-2">
          {markers.filter((m) => m.t <= duration).map((m, i) => (
            <Tip key={i} content={`${fmtClock(m.t)} · ${m.label}`}>
              <span className={cn("pointer-events-auto absolute top-0 size-2 -translate-x-1/2 rotate-45 rounded-[1px]",
                m.tone === "danger" ? "bg-danger" : m.tone === "caution" ? "bg-caution" : m.tone === "egress" ? "bg-egress" : "bg-signal")}
                    style={{ left: `${(m.t / Math.max(duration, 1)) * 100}%` }} />
            </Tip>
          ))}
        </div>
      </div>
      <span className="shrink-0 text-right text-sm tabular text-muted sm:w-28">{fmtClock(now)} / {fmtClock(duration)}</span>
    </div>
  );
}
