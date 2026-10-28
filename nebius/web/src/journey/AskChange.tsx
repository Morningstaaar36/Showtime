/** Venue changes asked in words: the venue agent proposes a patch, the server dry-runs it, the 3D
 * view previews it, and nothing is saved until the organizer applies it. The preview hook, the
 * proposal card and the input used by the "Ask or change anything" box. */
import { Check, CornerDownLeft, Lock, Sparkles, X } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { usePreviewPatch } from "@/api/queries";
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
function withProposedMarks(ops: PatchOpIn[], changes: ObjectChange[]): PatchOpIn[] {
  const added = changes.filter((c) => c.kind === "added" && c.what !== "zone");
  return [...ops, ...added.map((c) => annotateOp(c.id, { change: "proposed" }))];
}

/** Dry-runs a proposed edit and hands the result to the 3D preview. Nothing is saved. */
export function useEditPreview(project: ProjectDetail, onPreview?: (p: ProposalPreview | null) => void) {
  const preview = usePreviewPatch(project.id);
  const [dry, setDry] = useState<PatchPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const clear = () => { preview.reset(); setDry(null); setError(null); onPreview?.(null); };
  const start = (out: EditOut) => {
    if (out.status !== "proposed" || !out.patch) return;
    const venue = project.version.venue;
    preview.mutate({ patch: { ops: out.patch.ops } }, {
      onSuccess: (p) => {
        setDry(p);
        if (p.ok && p.venue) onPreview?.({ venue: p.venue, changes: diffVenues(venue, p.venue) });
      },
      onError: (e) => setError(e.message),
    });
  };
  return { dry, error, previewing: preview.isPending, start, clear };
}

/** A proposed edit: what it changes, whether it can be applied, and Apply / Discard. */
export function EditProposal({ project, out, dry, previewing, onApplied, onDiscard }: {
  project: ProjectDetail; out: EditOut; dry: PatchPreview | null; previewing: boolean;
  onApplied: () => void; onDiscard: () => void;
}) {
  const venue = project.version.venue;
  const names = useMemo(() => displayNames(venue), [venue]);
  const human = useMemo(() => textHumanizer(venue), [venue]);
  const { submit, pending } = useVenueEdit(project.id);

  if (out.status === "questions") {
    return <><p className="font-medium">{t("check.ai_questions")}</p><ul className="mt-1 list-disc pl-5 text-muted">{out.questions.map((q) => <li key={q}>{human(q)}</li>)}</ul></>;
  }
  if (out.status === "failed") return <p>{human(out.explanation) || t("check.ai_failed")}</p>;
  if (out.status !== "proposed") return null;
  const ops = out.patch?.ops ?? [];
  const conflicts = lockConflicts(venue, ops);
  const changes = dry?.ok && dry.venue ? diffVenues(venue, dry.venue) : [];
  const outdated = !!dry && dry.base_version !== project.current_version;
  const newOpenings = changes.filter((c) => c.kind === "added" && c.what !== "zone");
  const canApply = !!dry?.ok && conflicts.length === 0 && !outdated && !pending;
  const apply = () => submit(withProposedMarks(ops, changes), out.explanation || t("check.ai_change"),
                             () => { onApplied(); toast(t("check.applied_hint")); }, dry?.base_version);
  return (
    <div className="space-y-3">
      <div>
        <p className="flex items-center gap-1.5 font-semibold"><Sparkles className="size-4 text-signal" />{t("check.ai_proposal")}</p>
        {out.explanation && <p className="mt-1 text-muted">{human(out.explanation)}</p>}
      </div>
      <ul className="list-disc space-y-0.5 pl-5">{ops.map((o, i) => <li key={i}>{describeOp(o as Record<string, unknown>, (id) => names.get(id) ?? id)}</li>)}</ul>
      {previewing && <p className="flex items-center gap-2 text-muted"><Spinner />{t("check.previewing")}</p>}
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
        <Button variant="primary" className="min-h-11" disabled={!canApply} onClick={apply}><Check />{t("check.apply")}</Button>
        <Button className="min-h-11" onClick={onDiscard}><X />{t("check.discard")}</Button>
      </div>
    </div>
  );
}

/** The one-line input of the AI boxes: a sparkle (a spinner while busy), the text, Send. */
export function AskInput({ id, label, placeholder, sendLabel, value, busy, onChange, onSubmit }: {
  id: string; label: string; placeholder: string; sendLabel: string; value: string; busy: boolean;
  onChange: (v: string) => void; onSubmit: (v: string) => void;
}) {
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(value); }}
          className="flex items-center gap-2 rounded-[12px] border border-border bg-surface/95 p-1.5 pl-3 shadow-[var(--shadow-float)] backdrop-blur focus-within:border-signal focus-within:ring-2 focus-within:ring-signal/20">
      {busy ? <Spinner /> : <Sparkles className="size-4 shrink-0 text-signal" />}
      <label htmlFor={id} className="sr-only">{label}</label>
      <input id={id} value={value} onChange={(e) => onChange(e.target.value)} maxLength={500} placeholder={placeholder}
             className="min-h-11 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted/80" />
      <button type="submit" disabled={!value.trim() || busy} aria-label={sendLabel}
              className="grid size-11 place-items-center rounded-[8px] bg-signal text-signal-ink disabled:opacity-40">
        <CornerDownLeft className="size-4" />
      </button>
    </form>
  );
}
