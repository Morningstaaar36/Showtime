/** Real cases: a row of tiles on Home (each rebuilds a documented disaster and tests it; saved
 * cases can be written, changed and deleted here) and a
 * compact card on Your plan (what happened, the sources, what the simulation found here). */
import { BookOpenText, Copy, ExternalLink, History, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { useDeleteRealCase, useOpenRealCase, useRealCases } from "@/api/queries";
import { Confirm } from "@/components/ui/alert-dialog";
import { t } from "@/i18n";
import { fmtNum } from "@/lib/format";
import { CaseForm } from "./CaseForm";
import { blankFacts, type CaseFacts, factsOf, openTarget, type RealCase, type RealCaseCard as Card } from "./realCases";

type FormState = { initial: CaseFacts; editId?: string } | null;

/** Home › Events like yours › Learn from real cases: the shipped examples, the cases organizers
 * saved, and a tile to write a new one. */
export function RealCaseRow() {
  const cases = useRealCases();
  const open = useOpenRealCase();
  const remove = useDeleteRealCase();
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState>(null);
  const [deleting, setDeleting] = useState<RealCase | null>(null);
  // the button disables only after the next render, so a double click's second click still
  // fires: a ref is set at once and lets one request through per opening
  const opening = useRef(false);
  if (!cases.data) return null;
  // always through the server: it opens a tested project at once, and designs again a layout
  // that was never fixed or tested (a model's second answer may get it right)
  const pick = (id: string) => {
    if (opening.current) return;
    opening.current = true;
    open.mutate(id, {
      onSuccess: (out) => {
        // the designer's layout needs a fix before it can be tested: say what, in the editor
        if (out.status === "needs_fixes") toast.warning(t("realcase.needs_fixes"), { description: out.problems?.join(" ") || t("realcase.needs_fixes_hint"), duration: 15_000 });
        navigate(openTarget(out));
      },
      onError: (e) => toast.error(t("realcase.open_failed"), { description: e.message }),
      onSettled: () => { opening.current = false; },
    });
  };
  const small = "inline-flex min-h-9 items-center gap-1 rounded-[var(--radius-control)] px-2 text-xs font-medium text-muted hover:bg-surface-2 hover:text-ink";
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
            <li key={c.id} className="flex flex-col rounded-[var(--radius-panel)] bg-surface shadow-sm">
              <button type="button" onClick={() => pick(c.id)} disabled={open.isPending}
                      data-testid={`real-case-${c.id}`}
                      className="group flex h-full w-full flex-1 flex-col gap-1 rounded-[var(--radius-panel)] border-2 border-transparent p-3 text-left transition hover:border-signal focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal disabled:opacity-60">
                <span className="font-semibold leading-snug">{c.title}</span>
                <span className="text-xs text-muted">{c.lesson}</span>
                <span className="mt-auto inline-flex items-center gap-1 pt-1.5 text-xs font-semibold text-signal">
                  {busy ? <><Loader2 className="size-3.5 animate-spin" aria-hidden />{t("realcase.building")}</>
                    : c.project_id ? t("home.uc_open") : t("realcase.open")}
                </span>
              </button>
              <div className="flex flex-wrap items-center gap-1 border-t border-border px-2 py-1">
                <span className="mr-auto text-2xs text-muted">{t(`realcase.origin_${c.origin}`)}</span>
                {c.origin === "saved" ? (
                  <>
                    <button type="button" className={small} aria-label={t("realcase.edit_named", { title: c.title })}
                            onClick={() => setForm({ initial: factsOf(c), editId: c.id })}><Pencil className="size-3.5" aria-hidden />{t("realcase.edit")}</button>
                    <button type="button" className={small} aria-label={t("realcase.delete_named", { title: c.title })}
                            onClick={() => setDeleting(c)}><Trash2 className="size-3.5" aria-hidden />{t("realcase.delete")}</button>
                  </>
                ) : (
                  <button type="button" className={small} aria-label={t("realcase.copy_named", { title: c.title })}
                          onClick={() => setForm({ initial: { ...factsOf(c), title: t("realcase.copy_title", { title: c.title }).slice(0, 60) } })}>
                    <Copy className="size-3.5" aria-hidden />{t("realcase.copy")}
                  </button>
                )}
              </div>
            </li>
          );
        })}
        <li>
          <button type="button" onClick={() => setForm({ initial: blankFacts() })}
                  className="flex h-full min-h-28 w-full flex-col items-center justify-center gap-1 rounded-[var(--radius-panel)] border-2 border-dashed border-border p-3 text-center text-sm font-semibold text-signal transition hover:border-signal focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal">
            <Plus className="size-5" aria-hidden />{t("realcase.add")}
            <span className="text-xs font-normal text-muted">{t("realcase.add_hint")}</span>
          </button>
        </li>
      </ul>
      {form && <CaseForm key={form.editId ?? "new"} open onOpenChange={(v) => !v && setForm(null)} initial={form.initial} editId={form.editId} />}
      <Confirm open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)} danger
               title={t("realcase.delete_title", { title: deleting?.title ?? "" })} body={t("realcase.delete_body")}
               confirmLabel={t("realcase.delete")}
               onConfirm={() => deleting && remove.mutate(deleting.id, {
                 onSuccess: () => toast.success(t("realcase.deleted", { title: deleting.title })),
                 onError: (e) => toast.error(e.message),
               })} />
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
