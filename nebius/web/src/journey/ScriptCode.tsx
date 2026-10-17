import { Code } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { t } from "@/i18n";
import { scriptOf, type WithEvents } from "@/journey/scriptSource";
import { cn } from "@/lib/utils";

/** "AI-written scenario" badge plus the code behind "Show the code". Renders nothing for menu attacks. */
export function ScriptCode({ attack, className }: { attack: WithEvents | null | undefined; className?: string }) {
  const script = scriptOf(attack);
  if (!script) return null;
  const example = script.author === "rules";
  return (
    <div className={cn("mt-1.5 space-y-1", className)} data-testid="script-code">
      <Badge tone="signal" className="max-w-full whitespace-normal"><Code />{t(example ? "scripts.badge_example" : "scripts.badge")}</Badge>
      <details className="rounded-[8px] border border-border text-xs">
        <summary className="flex min-h-11 cursor-pointer items-center px-2 font-medium text-signal">{t("scripts.show_code")}</summary>
        <div className="space-y-1.5 border-t border-border p-2">
          <p className="text-muted">{t(example ? "scripts.explain_example" : "scripts.explain", { every: script.everyS })}</p>
          <pre className="max-h-72 overflow-auto rounded-[6px] bg-surface-2 p-2 font-mono text-2xs leading-relaxed"><code>{script.code}</code></pre>
          <p className="text-muted">{t("scripts.screening")}</p>
        </div>
      </details>
    </div>
  );
}
