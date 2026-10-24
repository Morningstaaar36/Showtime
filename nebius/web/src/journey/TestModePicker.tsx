/** Four ways to test a plan, as one compact choice above "Test this plan". */
import { Layers, Swords, WifiOff, Zap } from "lucide-react";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { TEST_MODES, type TestMode } from "./testModes";

const ICON: Record<TestMode, React.ReactNode> = {
  quick: <Zap />,
  standard: <Swords />,
  deep: <Layers />,
  offline: <WifiOff />,
};

export function TestModePicker({ value, onChange, disabled }: { value: TestMode; onChange: (m: TestMode) => void; disabled?: boolean }) {
  return (
    <div role="radiogroup" aria-label={t("check.mode_label")} className="grid grid-cols-4 gap-1 rounded-[var(--radius-control)] bg-surface-2 p-1">
      {TEST_MODES.map((m) => {
        const on = m.id === value;
        return (
          <button key={m.id} type="button" role="radio" aria-checked={on} disabled={disabled}
                  title={t(`check.mode_${m.id}_hint`)} onClick={() => onChange(m.id)}
                  className={cn("flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-[6px] px-1 text-xs font-medium transition [&_svg]:size-4",
                                on ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink")}>
            {ICON[m.id]}
            <span>{t(`check.mode_${m.id}`)}</span>
          </button>
        );
      })}
    </div>
  );
}
