import { ExternalLink, MessageCircleQuestion, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useAsk } from "@/api/queries";
import type { AskOut, Hotspot } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/misc";
import { ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { fmtClock, fmtNum } from "@/lib/format";
import { useUi } from "@/state/ui";

const SUGGESTIONS = ["Why is this red?", "Which exit are these people heading for?", "What would reduce the density here?"];

/** "Ask the venue": the Explainer answers from this run's numbers only. */
export function AskDialog({ open, onOpenChange, projectId, runId, hotspot }: {
  open: boolean; onOpenChange: (v: boolean) => void; projectId: string; runId: string | null; hotspot: Hotspot | null;
}) {
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<AskOut | null>(null);
  const ask = useAsk();
  const fly = useUi((s) => s.flyToPoint);
  // closing, or asking about another spot, drops any answer still on its way so it cannot
  // show up (or move the camera) for the wrong hotspot
  const resetAsk = ask.reset;
  const spot = hotspot ? `${hotspot.floor_id}:${hotspot.x}:${hotspot.y}:${hotspot.t_s}` : "";
  useEffect(() => { resetAsk(); setAnswer(null); }, [open, spot, runId, resetAsk]);
  const submit = (question: string) => {
    if (!question.trim()) return;
    setAnswer(null);
    ask.mutate({ project_id: projectId, run_id: runId, question,
                 hotspot: hotspot ? { floor_id: hotspot.floor_id, x: hotspot.x, y: hotspot.y, t_s: hotspot.t_s } : null }, {
      onSuccess: (a) => { setAnswer(a); if (a.camera_target) fly(a.camera_target.x, a.camera_target.y, a.camera_target.floor_id); },
    });
  };
  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) { setAnswer(null); setQ(""); } }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><MessageCircleQuestion className="size-5 text-signal" />{t("redteam.ask_title")}</DialogTitle>
          <DialogDescription>
            {hotspot ? t(hotspot.near ? "ui.askdialog.hotspot_near" : "ui.askdialog.hotspot", { ppm2: fmtNum(hotspot.peak_density_ppm2, 1), at: fmtClock(hotspot.t_s), near: hotspot.near ?? "" })
              : t("ui.askdialog.ask_busiest")} {t("ui.askdialog.only_numbers")}
          </DialogDescription>
        </DialogHeader>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); submit(q); }}>
          <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("redteam.ask_ph")} aria-label={t("ui.askdialog.question")} />
          <Button variant="primary" type="submit" disabled={ask.isPending || !q.trim()}>{t("ui.askdialog.ask")}</Button>
        </form>
        {!answer && !ask.isPending && (
          <div className="flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" onClick={() => { setQ(s); submit(s); }}
                      className="rounded-full border border-border px-2.5 py-1 text-xs text-muted hover:border-border-strong hover:text-ink">{s}</button>
            ))}
          </div>
        )}
        {ask.isPending && <p className="flex items-center gap-2 text-sm text-muted"><Spinner />{t("ui.askdialog.reading_the_run_data")}</p>}
        {ask.isError && <ErrorState message={ask.error.message} hint={(ask.error as { hint?: string }).hint} />}
        {answer && (
          <div className="space-y-2 rounded-[var(--radius-panel)] border border-border bg-surface-2 p-4">
            <p className="text-sm leading-relaxed">{answer.answer}</p>
            <p className="flex items-center gap-1.5 text-2xs text-muted">
              <ShieldCheck className="size-3.5 text-egress" />
              {answer.numbers_checked ? t("ui.askdialog.every_number_was_checked_against") : t("ui.askdialog.answer_withheld_numbers_it_could")}
            </p>
            {answer.sources.map((s) => (
              <a key={s.url} href={s.url} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-xs text-signal hover:underline">
                <ExternalLink className="size-3.5" />{s.title}
              </a>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
