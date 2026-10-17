/** The verdict at the top of Your plan: the finding from computed numbers, what the tests show
 * (the session's evaluation, never "confirmed" unless it is), and the key numbers, each with
 * what it is based on. The evacuation time (95%) sits next to the people still inside. */
import { ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import type * as React from "react";
import { Badge } from "@/components/ui/badge";
import { t } from "@/i18n";
import { Link } from "react-router";
import { type Evaluation, evaluationLabel, evaluationReason } from "@/lib/evidence";
import { cn } from "@/lib/utils";
import type { VerdictLevel } from "@/panels/verdict";

export interface KeyNumber {
  label: string;
  value: string;
  /** a second fact that belongs with the value (people still inside next to the 95% time) */
  detail?: string;
  /** what the number is based on, in organizer words */
  basis: string;
}

const TONE: Record<VerdictLevel, string> = {
  fails: "border-danger/35 bg-danger-soft",
  at_risk: "border-caution/35 bg-caution-soft",
  holds: "border-egress/35 bg-egress-soft",
  unknown: "border-border bg-surface-2",
};

const EVAL_TONE = { confirmed: "egress", partially_confirmed: "caution", failed: "danger", unconfirmed: "neutral" } as const;

export function VerdictBanner({ level, headline, under, reasons, evaluation, judge, numbers, action }: {
  level: VerdictLevel;
  headline: string;
  under: string;
  /** why the computed numbers fail or put the plan at risk */
  reasons: string[];
  evaluation: Evaluation | null | undefined;
  judge?: string | null;
  numbers: KeyNumber[];
  action?: React.ReactNode;
}) {
  const icon = level === "fails" ? <ShieldAlert className="text-danger" /> : level === "holds" ? <ShieldCheck className="text-egress" /> : <ShieldQuestion className="text-caution" />;
  const status = evaluation?.status ?? "unconfirmed";
  return (
    <section aria-label={t("yourplan.verdict")} className={cn("space-y-4 rounded-[var(--radius-panel)] border-2 p-5 shadow-sm", TONE[level])}>
      <div className="flex flex-wrap items-start gap-3">
        <span className="mt-0.5 [&_svg]:size-7">{icon}</span>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xl font-semibold leading-tight">{headline}</p>
            <Badge tone={EVAL_TONE[status] ?? "neutral"} className="text-sm">{evaluationLabel(evaluation)}</Badge>
          </div>
          <p className="max-w-prose text-sm" data-testid="verdict-why">
            {evaluationReason(evaluation)}{" "}
            <Link to="/help#verdict" className="font-medium text-signal underline-offset-4 hover:underline">{t("evidence.why.help")}</Link>
          </p>
          <p className="max-w-prose text-base">{under}</p>
          {reasons.length > 0 && <ul className="list-disc pl-5 text-sm">{reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
        </div>
        {action}
      </div>

      <ul className="grid gap-3 sm:grid-cols-3">
        {numbers.map((n, i) => (
          <li key={n.label} className={cn("rounded-[var(--radius-panel)] border border-t-4 border-border bg-surface p-4 shadow-sm", ["border-t-sky", "border-t-pink", "border-t-orange"][i % 3])}>
            <p className="text-sm text-muted">{n.label}</p>
            <p className="mt-0.5 text-2xl font-bold tabular">{n.value}</p>
            {n.detail && <p className="text-sm font-medium tabular">{n.detail}</p>}
            <p className="mt-1 text-xs text-muted">{n.basis}</p>
          </li>
        ))}
      </ul>

      {(evaluation?.reasons?.length || judge) && (
        <div className="space-y-1.5 rounded-[10px] bg-surface/70 p-3 text-sm">
          <p className="font-semibold">{t("yourplan.tests_show")}</p>
          {evaluation?.reasons && evaluation.reasons.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5">{evaluation.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          )}
          {judge && <p className="max-w-prose text-muted">{judge}</p>}
        </div>
      )}
    </section>
  );
}
