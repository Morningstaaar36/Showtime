/** Real cases: a row of tiles on Home (each rebuilds a documented disaster and tests it) and a
 * compact card on Your plan (what happened, the sources, what the simulation found here). */
import { ArrowRight, BookOpenText, ExternalLink, History, Loader2 } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { useOpenRealCase, useRealCases } from "@/api/queries";
import { t } from "@/i18n";
import { fmtNum } from "@/lib/format";
import { openTarget, type RealCaseCard as Card } from "./realCases";

/** Home › Events like yours › Learn from real cases. */
export function RealCaseRow() {
  const cases = useRealCases();
  const open = useOpenRealCase();
  const navigate = useNavigate();
  if (!cases.data?.length) return null;
  const pick = (id: string, projectId: string | null) => {
    if (projectId) {
      navigate(`/p/${projectId}`);
      return;
    }
    open.mutate(id, {
      onSuccess: (out) => navigate(openTarget(out)),
      onError: (e) => toast.error(t("realcase.open_failed"), { description: e.message }),
    });
  };
  return (
    <section aria-labelledby="rc-h" className="space-y-2">
      <div>
        <h3 id="rc-h" className="flex items-center gap-2 text-lg font-semibold"><History className="size-5 text-signal" aria-hidden />{t("realcase.title")}</h3>
        <p className="text-sm text-muted">{t("realcase.lead")}</p>
      </div>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {cases.data.map((c) => {
          const busy = open.isPending && open.variables === c.id;
          return (
            <li key={c.id}>
              <button type="button" onClick={() => pick(c.id, c.project_id)} disabled={open.isPending}
                      data-testid={`real-case-${c.id}`}
                      className="group flex h-full w-full flex-col gap-1 rounded-[var(--radius-panel)] border-2 border-transparent bg-surface p-3 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-signal focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal disabled:opacity-60">
                <span className="font-semibold leading-snug">{c.title}</span>
                <span className="text-xs text-muted">{c.lesson}</span>
                <span className="mt-auto inline-flex items-center gap-1 pt-1.5 text-xs font-semibold text-signal">
                  {busy ? <><Loader2 className="size-3.5 animate-spin" aria-hidden />{t("realcase.building")}</>
                    : <>{c.project_id ? t("home.uc_open") : t("realcase.open")}<ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" aria-hidden /></>}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Your plan › Overview: the case this venue rebuilds, in one compact card. */
export function RealCaseCard({ card, peak }: { card: Card; peak: { peak: number; where: string | null } | null }) {
  return (
    <section aria-labelledby="rcc-h" data-testid="real-case-card"
             className="space-y-2 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
      <h2 id="rcc-h" className="flex items-center gap-2 font-semibold">
        <BookOpenText className="size-4 text-signal" aria-hidden />{t("realcase.card_title", { incident: card.incident, date: card.date.slice(0, 4) })}
      </h2>
      <p className="max-w-prose text-sm">{card.what_happened} <span className="text-muted">{card.toll}</span></p>
      {peak && (
        <p className="text-sm font-medium tabular">
          {peak.where ? t("realcase.simulated", { peak: fmtNum(peak.peak, 1), where: peak.where }) : t("realcase.simulated_anywhere", { peak: fmtNum(peak.peak, 1) })}
        </p>
      )}
      {card.sources.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label={t("realcase.sources")}>
          {card.sources.map((s) => (
            <li key={s.url} className="max-w-full">
              <a href={s.url} target="_blank" rel="noreferrer" title={s.label}
                 className="inline-flex max-w-full items-center gap-1 text-signal underline-offset-4 hover:underline">
                <ExternalLink className="size-3 shrink-0" aria-hidden /><span className="truncate">{s.label}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
      <p className="text-2xs text-muted">{t("realcase.reconstruction")}</p>
    </section>
  );
}
