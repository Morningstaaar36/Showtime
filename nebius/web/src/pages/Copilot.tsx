import { CheckCircle2, ChevronDown, CircleAlert, Loader2, ShieldCheck, Wand2, XCircle } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { AgentGraph, type NodeStatus } from "@/panels/AgentGraph";

interface Action { title: string; why: string; how: string; priority: 1 | 2 | 3 }
interface Step {
  step: string; status: "running" | "done" | "warn" | "failed"; title?: string; detail?: string; project_id?: string;
  notes?: string[]; node?: string; review?: { summary: string; actions: Action[] };
}

/** Example events: a short chip label fills in the full sentence. */
const EXAMPLES = ["concert", "convocation", "festival", "conference"];

const STEP_TONE: Record<Step["status"], string> = {
  running: "border-signal/40 bg-signal-soft/50",
  done: "border-border bg-surface",
  warn: "border-caution/40 bg-caution-soft/60",
  failed: "border-danger/40 bg-danger-soft",
};
const PRIORITY_TONE: Record<Action["priority"], string> = {
  1: "bg-danger-soft text-danger", 2: "bg-caution-soft text-caution", 3: "bg-surface-3 text-muted",
};

/** Read the Copilot's JSON-lines stream, keeping one row per step (latest status wins). */
async function streamPlan(text: string, onStep: (s: Step) => void, signal: AbortSignal) {
  const res = await fetch("/api/v1/copilot/plan", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }), signal,
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null) as { message?: string } | null;
    throw new Error(body?.message ?? t("copilot.start_failed", { status: res.status }));
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) onStep(JSON.parse(line) as Step);
    }
  }
}

/** The Event Copilot: one sentence in, a planned and simulated project out. */
export function CopilotBox() {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [nodes, setNodes] = useState<Record<string, NodeStatus>>({});
  const [review, setReview] = useState<Step["review"] | null>(null);
  const [running, setRunning] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const ready = text.trim().length >= 8 && !running;

  // a step still spinning when the planner stops did not finish
  const failRunning = () => {
    setSteps((prev) => prev.map((p) => (p.status === "running" ? { ...p, status: "failed" } : p)));
    setNodes((prev) => Object.fromEntries(Object.entries(prev).map(([k, v]) => [k, v === "running" ? "failed" : v])));
  };

  const go = async (value: string) => {
    if (value.trim().length < 8 || running) return;
    setOpen(true); setSteps([]); setError(null); setProjectId(null); setRunning(true); setNodes({}); setReview(null);
    abort.current = new AbortController();
    try {
      await streamPlan(value.trim(), (s) => {
        if (s.project_id) setProjectId(s.project_id);
        if (s.node) setNodes((n) => ({ ...n, [s.node!]: s.status }));
        if (s.review) setReview(s.review);
        if (s.step === "error") { setError(s.title ?? t("copilot.failed")); failRunning(); return; }
        if (s.step === "finished") return;
        setSteps((prev) => {
          const k = prev.findIndex((p) => p.step === s.step);
          if (k < 0) return [...prev, s];
          const next = prev.slice(); next[k] = { ...prev[k], ...s }; return next;
        });
      }, abort.current.signal);
      void qc.invalidateQueries({ queryKey: ["projects"] });
    } catch (e) {
      if ((e as Error).name !== "AbortError") { setError((e as Error).message); failRunning(); }
    } finally {
      setRunning(false);
    }
  };
  const stop = () => { abort.current?.abort(); setOpen(false); };

  return (
    <div>
      <form onSubmit={(e) => { e.preventDefault(); void go(text); }}
            className="rounded-[var(--radius-panel)] border-2 border-border bg-surface p-2 transition focus-within:border-signal focus-within:ring-4 focus-within:ring-signal-soft">
        <label htmlFor="copilot-text" className="sr-only">{t("copilot.label")}</label>
        <textarea id="copilot-text" rows={3} value={text} onChange={(e) => setText(e.target.value)} maxLength={600}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void go(text); } }}
                  placeholder={t("copilot.ph")}
                  className="block w-full resize-none bg-transparent px-2 py-1.5 text-base outline-none placeholder:text-muted/80" />
        <div className="flex flex-wrap items-center justify-end gap-2 px-1 pb-1">
          <span className="mr-auto hidden text-xs text-muted sm:inline">{t("copilot.enter_hint")}</span>
          <Button type="submit" variant={ready ? "primary" : "secondary"} size="lg" disabled={!ready}>
            {running ? <Loader2 className="animate-spin" /> : <Wand2 />}{t("copilot.go")}
          </Button>
        </div>
      </form>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted">{t("copilot.try")}</span>
        {EXAMPLES.map((k) => (
          <button key={k} type="button" onClick={() => setText(t(`copilot.ex_${k}`))} title={t(`copilot.ex_${k}`)}
                  className="min-h-11 rounded-full bg-pink-soft px-3 text-sm font-medium text-pink hover:brightness-95">
            {t(`copilot.ex_${k}_chip`)}
          </button>
        ))}
      </div>

      <Dialog open={open} onOpenChange={(v) => { if (!v) stop(); }}>
        <DialogContent wide className="max-h-[94vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2.5 text-xl">
              <span className="grid size-9 place-items-center rounded-full bg-pink-soft text-pink [&_svg]:size-5"><Wand2 aria-hidden /></span>
              {t("copilot.dialog_title")}
            </DialogTitle>
            <DialogDescription className="line-clamp-2 text-base">“{text.trim()}”</DialogDescription>
          </DialogHeader>

          <ol className="space-y-2" aria-live="polite" aria-label={t("copilot.steps")}>
            {steps.map((s) => (
              <li key={s.step} className={cn("flex gap-3 rounded-[var(--radius-control)] border p-3", STEP_TONE[s.status])}>
                <span className="mt-0.5 [&_svg]:size-5">
                  {s.status === "running" ? <Loader2 className="animate-spin text-signal" aria-label={t("copilot.status_running")} />
                    : s.status === "done" ? <CheckCircle2 className="text-egress" aria-label={t("copilot.status_done")} />
                    : s.status === "warn" ? <CircleAlert className="text-caution" aria-label={t("copilot.status_warn")} />
                    : <XCircle className="text-danger" aria-label={t("copilot.status_failed")} />}
                </span>
                <div className="min-w-0">
                  <p className="font-medium">{s.title}</p>
                  {s.detail && <p className="mt-0.5 text-sm text-muted">{s.detail}</p>}
                </div>
              </li>
            ))}
            {running && steps.length === 0 && (
              <li className="flex items-center gap-3 rounded-[var(--radius-control)] border border-border p-3 text-muted">
                <Loader2 className="size-5 animate-spin text-signal" aria-hidden />{t("copilot.starting")}
              </li>
            )}
          </ol>

          {error && (
            <p role="alert" className="flex gap-2 rounded-[var(--radius-control)] border border-danger/30 bg-danger-soft p-3 text-sm">
              <XCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />{error}
            </p>
          )}

          {review && review.actions.length > 0 && (
            <section aria-labelledby="officer-h" className="rounded-[var(--radius-panel)] border-2 border-egress/30 bg-egress-soft/40 p-4">
              <h3 id="officer-h" className="flex items-center gap-2 font-semibold"><ShieldCheck className="size-5 text-egress" aria-hidden />{t("copilot.officer")}</h3>
              <p className="mt-1 text-sm">{review.summary}</p>
              <ol className="mt-3 space-y-2">
                {review.actions.map((a, i) => (
                  <li key={i} className="flex gap-3 rounded-[var(--radius-control)] bg-surface p-3 text-sm">
                    <span className={cn("grid size-6 shrink-0 place-items-center rounded-full text-xs font-bold tabular", PRIORITY_TONE[a.priority])}
                          title={t("copilot.priority", { n: a.priority })}>
                      <span className="sr-only">{t("copilot.priority", { n: a.priority })}</span><span aria-hidden>{a.priority}</span>
                    </span>
                    <div className="min-w-0"><p className="font-semibold">{a.title}</p><p className="text-muted">{a.why} {a.how}</p></div>
                  </li>
                ))}
              </ol>
            </section>
          )}

          <details className="group rounded-[var(--radius-panel)] border border-border">
            <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-3 text-sm font-medium">
              <ChevronDown className="size-4 text-muted transition group-open:rotate-180" aria-hidden />{t("copilot.show_graph")}
            </summary>
            <div className="flex justify-center border-t border-border p-3"><AgentGraph status={nodes} /></div>
          </details>

          <DialogFooter className="items-center">
            <p className="mr-auto max-w-md text-xs text-muted">{t("copilot.trust")}</p>
            {running ? <Button size="lg" onClick={stop}>{t("common.cancel")}</Button>
              : <Button size="lg" onClick={() => setOpen(false)}>{t("common.close")}</Button>}
            {projectId && (
              <Button variant="primary" size="lg" onClick={() => { setOpen(false); navigate(`/p/${projectId}/expert?tour=1`); }}>
                {t("copilot.open")}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
