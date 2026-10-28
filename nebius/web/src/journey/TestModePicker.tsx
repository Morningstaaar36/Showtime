/** The ways to test a plan (GET /test_modes), as one compact choice above "Test this plan". */
import { Gauge, Layers, Swords, WifiOff, Zap } from "lucide-react";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import type { TestModeInfo } from "./testModes";

/** Icons for the server's modes; a mode this page does not know yet gets a plain one. */
const ICON: Record<string, React.ReactNode> = {
  quick: <Zap />,
  standard: <Swords />,
  deep: <Layers />,
  offline: <WifiOff />,
};

export function TestModePicker({ modes, value, onChange, disabled }: {
  modes: readonly TestModeInfo[]; value: string; onChange: (m: string) => void; disabled?: boolean;
}) {
  return (
    <div role="radiogroup" aria-label={t("check.mode_label")} className="grid gap-1 rounded-[var(--radius-control)] bg-surface-2 p-1"
         style={{ gridTemplateColumns: `repeat(${modes.length}, minmax(0, 1fr))` }}>
      {modes.map((m) => {
        const on = m.id === value;
        return (
          <button key={m.id} type="button" role="radio" aria-checked={on} disabled={disabled}
                  title={t(`check.mode_${m.id}_hint`)} onClick={() => onChange(m.id)}
                  className={cn("flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-[6px] px-1 text-xs font-medium transition [&_svg]:size-4",
                                on ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink")}>
            {ICON[m.id] ?? <Gauge />}
            <span>{t(`check.mode_${m.id}`)}</span>
          </button>
        );
      })}
    </div>
  );
}
