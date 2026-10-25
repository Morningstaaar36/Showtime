/** What the agents did with their tools during a test, in plain words ("Red team searched the
 * web: 3 sources", "12 similar real incidents found", "Tier 2 simulation in the sandbox"). */
import { Wrench } from "lucide-react";
import type { AgentLine } from "@/api/useSessionStream";
import { t } from "@/i18n";

export function ToolCalls({ feed, max = 6 }: { feed: AgentLine[]; max?: number }) {
  // simulations have their own feed (Sandboxes); these are the agents' other tools
  const calls = feed.filter((l) => l.type === "tool_call" && l.agent !== "run_sim").slice(-max).reverse();
  if (!calls.length) return null;
  return (
    <section aria-labelledby="tools-h" className="rounded-[var(--radius-panel)] border border-border bg-surface p-3 shadow-sm" data-testid="tool-calls">
      <h2 id="tools-h" className="flex items-center gap-1.5 text-sm font-semibold"><Wrench className="size-4 text-signal" aria-hidden />{t("work.tools_title")}</h2>
      <ul className="mt-2 space-y-1 text-sm">
        {calls.map((c) => <li key={c.seq} className="text-muted">{c.summary}</li>)}
      </ul>
    </section>
  );
}
