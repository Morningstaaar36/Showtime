/** "Ask AI to change the venue": the venue agent proposes a patch, the server dry-runs it, the
 * 3D view previews it, and nothing is saved until the organizer applies it. */
import { AlertTriangle, Check, CornerDownLeft, Lock, Sparkles, X } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { usePreviewPatch, useTextEdit } from "@/api/queries";
import type { EditOut, PatchOpIn, PatchPreview, ProjectDetail, Venue } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/misc";
import { t } from "@/i18n";
import { annotateOp, lockConflicts } from "@/lib/annotations";
import { diffVenues, type ObjectChange } from "@/lib/venueDiff";
import { displayNames, textHumanizer } from "@/lib/venueText";
import { describeOp } from "@/panels/describe";
import { useVenueEdit } from "./useVenueEdit";

export interface ProposalPreview { venue: Venue; changes: ObjectChange[] }

/** The ops to save: the proposal, then every new exit or obstacle marked as proposed. */
export function withProposedMarks(ops: PatchOpIn[], changes: ObjectChange[]): PatchOpIn[] {
  const added = changes.filter((c) => c.kind === "added" && c.what !== "zone");
  return [...ops, ...added.map((c) => annotateOp(c.id, { change: "proposed" }))];
}

export function AskChange({ project, onPreview }: { project: ProjectDetail; onPreview: (p: ProposalPreview | null) => void }) {
  const venue = project.version.venue;
  const names = useMemo(() => displayNames(venue), [venue]);
  const human = useMemo(() => textHumanizer(venue), [venue]);
  const edit = useTextEdit(project.id);
  const preview = usePreviewPatch(project.id);
  const { submit, pending } = useVenueEdit(project.id);
  const [text, setText] = useState("");
  const [out, setOut] = useState<EditOut | null>(null);
  const [dry, setDry] = useState<PatchPreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => { setOut(null); setDry(null); setError(null); onPreview(null); };
  const ask = (value: string) => {
    if (!value.trim() || edit.isPending) return;
    reset();
    edit.mutate({ text: value, apply: false }, {
      onSuccess: (r) => {
        setOut(r);
        if (r.status !== "proposed" || !r.patch) return;
        preview.mutate({ patch: { ops: r.patch.ops } }, {
          onSuccess: (p) => {
            setDry(p);
            if (p.ok && p.venue) onPreview({ venue: p.venue, changes: diffVenues(venue, p.venue) });
          },
          onError: (e) => setError(e.message),
        });
      },
      onError: (e) => {
        const err = e as ApiError;
        setError(err.code === "llm_unavailable" || err.status === 503 ? t("check.ai_unavailable") : err.message);
      },
    });
  };

  const ops = out?.patch?.ops ?? [];
  const conflicts = lockConflicts(venue, ops);
  const changes = dry?.ok && dry.venue ? diffVenues(venue, dry.venue) : [];
  const outdated = !!dry && dry.base_version !== project.current_version;
  const newOpenings = changes.filter((c) => c.kind === "added" && c.what !== "zone");
  const canApply = !!dry?.ok && conflicts.length === 0 && !outdated && !pending;
  const busy = edit.isPending || preview.isPending;

  return (
    <div className="pointer-events-auto w-full max-w-2xl space-y-2">
      {(out || error) && (
        <section aria-live="polite" aria-label={t("check.ai_proposal")}
                 className="max-h-[45vh] overflow-y-auto rounded-[12px] border border-border bg-surface p-4 text-sm shadow-[var(--shadow-float)]">
          {error && <p className="flex gap-2"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" />{error}</p>}
          {out?.status === "questions" && (
            <><p className="font-medium">{t("check.ai_questions")}</p><ul className="mt-1 list-disc pl-5 text-muted">{out.questions.map((q) => <li key={q}>{human(q)}</li>)}</ul></>
          )}
          {out?.status === "failed" && <p>{human(out.explanation) || t("check.ai_failed")}</p>}
          {out?.status === "proposed" && (
            <div className="space-y-3">
              <div>
                <p className="flex items-center gap-1.5 font-semibold"><Sparkles className="size-4 text-signal" />{t("check.ai_proposal")}</p>
                {out.explanation && <p className="mt-1 text-muted">{human(out.explanation)}</p>}
              </div>
              <ul className="list-disc space-y-0.5 pl-5">{ops.map((o, i) => <li key={i}>{describeOp(o as Record<string, unknown>, (id) => names.get(id) ?? id)}</li>)}</ul>
              {preview.isPending && <p className="flex items-center gap-2 text-muted"><Spinner />{t("check.previewing")}</p>}
              {dry && !dry.ok && (
                <div className="rounded-[8px] bg-danger-soft p-2.5">
                  <p className="font-medium">{t("check.cannot_apply")}</p>
                  <ul className="mt-1 list-disc pl-5">{dry.problems.map((p) => <li key={p}>{human(p)}</li>)}</ul>
                </div>
              )}
              {conflicts.length > 0 && (
                <div className="rounded-[8px] bg-danger-soft p-2.5">
                  {conflicts.map((c) => <p key={`${c.id}:${c.op}`} className="flex gap-1.5"><Lock className="mt-0.5 size-3.5 shrink-0" />{t("check.conflict", { name: names.get(c.id) ?? c.id })}</p>)}
                  <p className="mt-1 text-muted">{t("check.conflict_hint")}</p>
                </div>
              )}
              {dry?.ok && changes.length > 0 && <p className="text-muted">{t("check.preview_shown", { n: changes.length })}</p>}
              {newOpenings.length > 0 && <p className="rounded-[8px] bg-caution-soft p-2.5">{t("check.new_marked_proposed")}</p>}
              {outdated && <p className="text-caution">{t("check.preview_outdated")}</p>}
              <div className="flex flex-wrap gap-2">
                <Button variant="primary" disabled={!canApply}
                        onClick={() => submit(withProposedMarks(ops, changes), out.explanation || t("check.ai_change"), () => { reset(); setText(""); toast(t("check.applied_hint")); })}>
                  <Check />{t("check.apply")}
                </Button>
                <Button onClick={reset}><X />{t("check.discard")}</Button>
              </div>
            </div>
          )}
        </section>
      )}
      <form onSubmit={(e) => { e.preventDefault(); ask(text); }}
            className="flex items-center gap-2 rounded-[12px] border border-border bg-surface/95 p-1.5 pl-3 shadow-[var(--shadow-float)] backdrop-blur focus-within:border-signal focus-within:ring-2 focus-within:ring-signal/20">
        {busy ? <Spinner /> : <Sparkles className="size-4 shrink-0 text-signal" />}
        <label htmlFor="ask-change" className="sr-only">{t("check.ask_label")}</label>
        <input id="ask-change" value={text} onChange={(e) => setText(e.target.value)} maxLength={500}
               placeholder={busy ? t("tools.thinking") : t("check.ask_ph")}
               className="min-h-11 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted/80" />
        <button type="submit" disabled={!text.trim() || busy} aria-label={t("check.ask_send")}
                className="grid size-11 place-items-center rounded-[8px] bg-signal text-signal-ink disabled:opacity-40">
          <CornerDownLeft className="size-4" />
        </button>
      </form>
    </div>
  );
}
