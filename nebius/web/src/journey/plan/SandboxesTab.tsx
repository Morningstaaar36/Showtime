/** Your plan › Sandboxes: where the AI's code ran and what the sealed sandboxes proved, in one
 * place: the AI-written scenarios with their code and outcome, Rewind (the same second, several
 * sandboxes), the stress test at scale, and every run of the test with its sandbox state. */
import { Ban, CircleCheck, OctagonX, Bug } from "lucide-react";
import type { Attack } from "@/api/types";
import type { SessionView } from "@/api/useSessionStream";
import { Badge } from "@/components/ui/badge";
import { t } from "@/i18n";
import { SandboxFeed, sandboxWhy } from "@/journey/SandboxFeed";
import { ScriptCode } from "@/journey/ScriptCode";
import { RewindPanel } from "./RewindPanel";
import { sandboxRows, scriptOutcomes } from "./sandboxes";
import { StressPanel } from "./StressPanel";

export function SandboxesTab({ view, attacks, sessionId, projectId, worstTitle, human }: {
  view: SessionView; attacks: Attack[]; sessionId: string | null; projectId: string; worstTitle: string | null; human: (s: string) => string;
}) {
  const { rows, recorded } = sandboxRows(view);
  const scripts = scriptOutcomes(view, attacks);
  return (
    <div className="space-y-6" data-testid="sandboxes-tab">
      <p className="max-w-prose text-muted">{t("plan.sbx_lead")}</p>

      <section aria-labelledby="sbx-scripts-h" className="space-y-3">
        <h2 id="sbx-scripts-h" className="text-lg font-semibold">{t("plan.sbx_scripts")}</h2>
        {scripts.length === 0 ? <p className="text-sm text-muted">{t("plan.sbx_no_scripts")}</p> : (
          <ul className="grid gap-3 lg:grid-cols-2">
            {scripts.map(({ attack, run }) => {
              const why = run ? sandboxWhy(run) : null;
              const state = run?.script?.state ?? null;
              return (
                <li key={attack.attack_id} className="rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm" data-testid="sbx-script">
                  <div className="flex items-start justify-between gap-3">
                    <p className="font-semibold">{human(attack.title)}</p>
                    {state === "ran" && <Badge tone="egress"><CircleCheck />{t("plan.sbx_ran")}</Badge>}
                    {state === "refused" && <Badge tone="danger"><Ban />{t("plan.sbx_refused")}</Badge>}
                    {state === "stopped" && <Badge tone="caution"><OctagonX />{t("plan.sbx_stopped")}</Badge>}
                    {state === "error" && <Badge tone="caution"><Bug />{t("plan.sbx_error")}</Badge>}
                  </div>
                  {why && <p className="mt-1 text-sm">{why.text}</p>}
                  <ScriptCode attack={attack} />
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {sessionId && (
        // one above the other: both end in a table of several columns that needs the full width
        <div className="grid gap-4">
          <RewindPanel sessionId={sessionId} worstTitle={worstTitle} canRewind={attacks.length > 0} />
          <StressPanel projectId={projectId} hasTest />
        </div>
      )}

      <section aria-labelledby="sbx-runs-h" className="space-y-2">
        <h2 id="sbx-runs-h" className="text-lg font-semibold">{t("plan.sbx_runs")}</h2>
        {!recorded && rows.length > 0 && <p className="text-sm text-muted">{t("plan.sbx_not_recorded")}</p>}
        <SandboxFeed runs={rows} />
      </section>
    </div>
  );
}
