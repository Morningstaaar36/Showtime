/** "Not right yet?": the organizer's words go back to the designer, which revises its own
 * design in the same rounds (check, critique, revise) and saves a new version. Shown only for a
 * venue designed from words (it has a stored design to revise). */
import { Loader2, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import type { Venue } from "@/api/types";
import { useRedesign, useStartRedesign } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { t } from "@/i18n";

export function canRedesign(venue: Venue | undefined): boolean {
  const gen = (venue?.extensions as Record<string, unknown> | undefined)?.generated as { spec?: unknown; description?: unknown } | undefined;
  return !!gen?.spec && typeof gen.description === "string";
}

export function RedesignBox({ projectId, venue }: { projectId: string; venue: Venue }) {
  const [text, setText] = useState("");
  const job = useRedesign(projectId);
  const start = useStartRedesign(projectId);
  const status = job.data?.status;
  const announced = useRef<string | null>(null);
  useEffect(() => {
    const key = `${status}:${job.data?.version ?? ""}`;
    if (announced.current === null) { announced.current = key; return; } // not the one already on the page
    if (key === announced.current) return;
    announced.current = key;
    if (status === "done" && job.data?.version) { toast.success(t("design.redesign_done", { n: job.data.version })); setText(""); }
    if (status === "failed") toast.error(t("design.redesign_failed", { why: job.data?.error ?? "" }));
  }, [status, job.data?.version, job.data?.error]);
  if (!canRedesign(venue)) return null;
  const busy = status === "designing" || start.isPending;
  const s = job.data?.stage;
  const stage = s?.stage ? t(`realcase.stage_${s.stage}`, { n: s.round ?? 1, of: s.of ?? 1 }) : "";
  return (
    <section aria-labelledby="redesign-h" className="space-y-2 rounded-[10px] border border-border p-3">
      <h2 id="redesign-h" className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="size-4 text-signal" />{t("design.redesign_title")}</h2>
      <p className="text-xs text-muted">{t("design.redesign_lead")}</p>
      <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (text.trim().length >= 3) start.mutate(text.trim(), { onError: (err) => toast.error((err as Error).message) }); }}>
        <Textarea aria-label={t("design.redesign_title")} rows={2} maxLength={600} value={text} disabled={busy}
                  placeholder={t("design.redesign_ph")} onChange={(e) => setText(e.target.value)} className="text-sm" />
        <Button type="submit" size="sm" variant="secondary" disabled={busy || text.trim().length < 3}>
          {busy ? <Loader2 className="animate-spin" /> : <Sparkles />}{busy ? t("design.redesign_running", { stage }) : t("design.redesign_go")}
        </Button>
      </form>
    </section>
  );
}
