/** "Ask or change anything" (N15): one box for the whole journey. The server sorts the sentence
 * (the AI, else keywords): an edit is previewed in 3D and saved only with Apply, a question is
 * answered from the run's numbers, a what-if shows instant estimates computed in code, an
 * analysis shows what code run in a sandbox computed (and the code), and a request for a screen
 * goes there. Reusable: pass the screen, the session and the preview. */
import { AlertTriangle, Calculator, ExternalLink, ShieldCheck, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { type AskAnswer, type AskAnythingOut, type AskScreen, type AskTarget, type AskWhatIf, useAskAnything } from "@/api/queries";
import type { ProjectDetail } from "@/api/types";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { textHumanizer } from "@/lib/venueText";
import { useUi } from "@/state/ui";
import { AnalysisCard } from "./AnalysisCard";
import { AskInput, EditProposal, type ProposalPreview, useEditPreview } from "./AskChange";
import { type AskError, askError, cappedNote, intentMeta, navAction, retryWithExit, whatIfChips, whatIfRows } from "./askModel";

export interface AskAnythingProps {
  project: ProjectDetail;
  /** The screen the box is on: the venue check or Your plan. */
  context: AskScreen;
  /** The tested plan being read: questions use its runs, the report link opens its report. */
  sessionId?: string | null;
  /** Show (or clear, with null) a proposed edit in 3D. The edit card also works without it. */
  onPreview?: (p: ProposalPreview | null) => void;
  className?: string;
}

const CHIP = "min-h-11 rounded-full border border-border bg-surface px-3 text-left text-sm hover:border-signal hover:bg-signal-soft";

export function AskAnything({ project, context, sessionId = null, onPreview, className }: AskAnythingProps) {
  const ask = useAskAnything(project.id);
  const proposal = useEditPreview(project, onPreview);
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [text, setText] = useState("");
  const [out, setOut] = useState<AskAnythingOut | null>(null);

  const go = (target: AskTarget) => {
    const a = navAction(target, project.id, sessionId);
    if (a.kind === "open") {
      const w = window.open(a.href, "_blank");
      if (w) w.opener = null;
    } else if (a.to.split("?")[0] !== pathname) navigate(a.to);
  };
  const close = () => { ask.reset(); setOut(null); proposal.clear(); };
  const send = (value: string) => {
    const v = value.trim();
    if (v.length < 2 || ask.isPending) return;
    close();
    setText(v);
    ask.mutate({ text: v, context, session_id: sessionId }, {
      onSuccess: (r) => {
        setOut(r);
        if (r.intent === "edit") proposal.start(r.result);
        if (r.intent === "navigate") go(r.result.target);
        if (r.intent === "question") flyToHotspot(r.result);
      },
    });
  };

  const err = ask.isError ? askError(ask.error) : null;
  const meta = intentMetaOf(out, err);
  const nav = out?.intent === "navigate" ? navAction(out.result.target, project.id, sessionId) : null;
  const busy = ask.isPending || proposal.previewing;

  return (
    <div className={cn("pointer-events-auto w-full max-w-2xl space-y-2", className)}>
      {(out || err) && (
        <section aria-live="polite" aria-label={t("ask.result")}
                 className="max-h-[45vh] space-y-3 overflow-y-auto rounded-[var(--radius-panel)] border border-border bg-surface p-4 text-sm shadow-[var(--shadow-float)]">
          <div className="-mr-2 -mt-2 flex items-center gap-2">
            {meta && <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold", meta.tone)}><meta.icon className="size-3.5" />{meta.label}</span>}
            {out?.routed_by === "keywords" && <span className="text-xs text-muted">{t("ask.by_keywords")}</span>}
            <button type="button" onClick={close} aria-label={t("ask.close")}
                    className="ml-auto grid size-11 shrink-0 place-items-center rounded-[8px] text-muted hover:bg-surface-2 hover:text-ink">
              <X className="size-4" />
            </button>
          </div>
          {err && <ErrorCard err={err} onRetry={(exit) => send(retryWithExit(text, err.unknown, exit))} />}
          {out?.intent === "edit" && (
            <>
              {proposal.error && <p className="flex gap-2"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" />{proposal.error}</p>}
              <EditProposal project={project} out={out.result} dry={proposal.dry} previewing={proposal.previewing}
                            onApplied={() => { close(); setText(""); }} onDiscard={close} />
            </>
          )}
          {out?.intent === "question" && <AnswerCard answer={out.result} project={project} />}
          {out?.intent === "what_if" && <WhatIfCard result={out.result} onPick={send} />}
          {out?.intent === "analyse" && (
            <AnalysisCard status={out.result.status} output={out.result.output} code={out.result.code}
                          answer={out.result.answer} numbersChecked={out.result.numbers_checked} plan={out.result.plan}
                          runtimeS={out.result.runtime_s} sandbox={out.result.sandbox} basis={out.result.basis}
                          stderrTail={out.result.stderr_tail} problems={out.result.problems} />
          )}
          {nav?.kind === "open" && (
            <div className="space-y-1">
              <p>{t("ask.report_opened")}</p>
              <a href={nav.href} target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center gap-1.5 font-medium text-signal hover:underline">
                <ExternalLink className="size-4" />{t("ask.open_report")}
              </a>
            </div>
          )}
          {nav?.kind === "route" && <p>{nav.to.split("?")[0] === pathname ? t("ask.here") : t("ask.going")}</p>}
          {out?.intent === "other" && <Examples lead={t("ask.help")} examples={out.result.examples} onPick={send} />}
        </section>
      )}
      <AskInput id="ask-anything" label={t("ask.label")} sendLabel={t("ask.send")} value={text} busy={busy}
                placeholder={busy ? t("ask.thinking") : t(context === "plan" ? "ask.ph_plan" : "ask.ph")}
                onChange={setText} onSubmit={send} />
    </div>
  );
}

function intentMetaOf(out: AskAnythingOut | null, err: AskError | null) {
  const intent = out?.intent ?? err?.intent ?? null;
  return intent ? intentMeta(intent) : null;
}

/** Point the 3D view at the hotspot an answer is about (when the run has one). */
function flyToHotspot(answer: AskAnswer) {
  const hotspot = answer.context?.hotspot as { peak_density_people_per_m2?: number | null } | undefined;
  const c = answer.camera_target;
  if (c && hotspot?.peak_density_people_per_m2 != null) useUi.getState().flyToPoint(c.x, c.y, c.floor_id);
}

function ErrorCard({ err, onRetry }: { err: AskError; onRetry: (exit: string) => void }) {
  return (
    <div className="space-y-2" role="alert">
      <p className="flex gap-2"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" />{err.text}</p>
      {err.hint && <p className="text-muted">{err.hint}</p>}
      {err.exits.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {err.exits.map((name) => <button key={name} type="button" className={CHIP} onClick={() => onRetry(name)}>{name}</button>)}
        </div>
      )}
    </div>
  );
}

function AnswerCard({ answer, project }: { answer: AskAnswer; project: ProjectDetail }) {
  const venue = project.version.venue;
  const human = useMemo(() => textHumanizer(venue), [venue]);
  return (
    <div className="space-y-2">
      <p className="text-base leading-relaxed">{human(answer.answer)}</p>
      <p className="flex items-center gap-1.5 text-xs text-muted">
        <ShieldCheck className="size-3.5 shrink-0 text-egress" />{answer.numbers_checked ? t("ask.checked") : t("ask.unchecked")}
      </p>
      <p className="text-xs text-muted">{t("ask.based_on", { basis: answer.basis })}</p>
      {answer.sources.map((s) => (
        <a key={s.url} href={s.url} target="_blank" rel="noreferrer" className="flex min-h-11 items-center gap-1.5 text-signal hover:underline">
          <ExternalLink className="size-4 shrink-0" />{s.title}
        </a>
      ))}
    </div>
  );
}

function WhatIfCard({ result, onPick }: { result: AskWhatIf; onPick: (text: string) => void }) {
  const p = result.params;
  if (!p.changed) return <Examples lead={t("ask.nothing_to_try")} examples={[t("ask.ex_double"), t("ask.ex_rain")]} onPick={onPick} />;
  const capped = cappedNote(p);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-caution-soft px-2.5 py-1 text-xs font-semibold text-caution">
          <Calculator className="size-3.5" />{t("ask.instant")}
        </span>
        {whatIfChips(p).map((c) => <span key={c} className="rounded-full border border-border px-2.5 py-1 text-xs">{c}</span>)}
      </div>
      {capped && <p className="text-caution">{capped}</p>}
      <table className="w-full">
        <thead>
          <tr className="text-xs text-muted">
            <th className="py-1 text-left font-normal"><span className="sr-only">{t("ask.instant")}</span></th>
            <th className="py-1 text-right font-normal">{t("ask.now")}</th>
            <th className="py-1 text-right font-normal">{t("ask.what_if")}</th>
          </tr>
        </thead>
        <tbody>
          {whatIfRows(result).map((r) => (
            <tr key={r.key} className="border-t border-border">
              <th scope="row" className="py-1.5 text-left font-normal text-muted">{r.label}</th>
              <td className="tabular py-1.5 text-right">{r.before}</td>
              <td className={cn("tabular py-1.5 text-right font-semibold", r.worse && "text-danger")}>{r.after}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-muted">{t("ask.instant_note")}</p>
    </div>
  );
}

function Examples({ lead, examples, onPick }: { lead: string; examples: string[]; onPick: (text: string) => void }) {
  return (
    <div className="space-y-2">
      <p>{lead}</p>
      <div className="flex flex-wrap gap-1.5">
        {examples.map((e) => <button key={e} type="button" className={CHIP} onClick={() => onPick(e)}>{e}</button>)}
      </div>
    </div>
  );
}
