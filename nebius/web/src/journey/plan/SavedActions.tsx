/** Staff and equipment actions in plain words: what, when, and who (never raw event types). */
import { Link } from "react-router";
import { t } from "@/i18n";
import { fmtClock } from "@/lib/format";
import { describeEvent } from "@/panels/describe";
import type { PlanAction } from "@/types/generated";

interface ActionText {
  what: string;
  when: string;
  staff: string;
}

export function actionText(a: PlanAction, name: (id: string) => string): ActionText {
  const what = a.event ? describeEvent(a.event as Record<string, unknown>, name) : t("yourplan.checklist_item");
  return {
    what: a.label ? `${a.label}: ${what}` : what,
    when: t("yourplan.action_when", { from: fmtClock(a.start_s), to: fmtClock(a.end_s) }),
    staff: a.resources.map((r) => `${r.quantity} × ${r.resource_id}`).join(", ") || t("yourplan.no_staff"),
  };
}

function ActionLine({ action, name }: { action: PlanAction; name: (id: string) => string }) {
  const a = actionText(action, name);
  return (
    <li className="rounded-[8px] border border-border p-2.5 text-sm">
      <p className="font-medium">{a.what}</p>
      <p className="text-muted tabular">{a.when} · {a.staff}</p>
    </li>
  );
}

export function SavedActions({ actions, version, projectId, name }: {
  actions: PlanAction[]; version: number; projectId: string; name: (id: string) => string;
}) {
  if (!actions.length) return null;
  return (
    <section aria-labelledby="saved-h" className="space-y-2 rounded-[10px] border border-border bg-surface p-4">
      <h2 id="saved-h" className="font-semibold">{t("yourplan.saved_plan")}</h2>
      <p className="text-xs text-muted">{t("yourplan.saved_plan_body", { n: version })}</p>
      <ul className="space-y-2">{actions.map((a) => <ActionLine key={a.action_id} action={a} name={name} />)}</ul>
      <Link className="flex min-h-11 items-center text-sm text-signal underline-offset-4 hover:underline" to={`/p/${projectId}/describe`}>{t("yourplan.edit_actions")}</Link>
    </section>
  );
}
