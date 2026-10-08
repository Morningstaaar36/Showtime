import { CheckCircle2, CircleAlert, Loader2, Sparkles, XCircle } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { AgentGraph, type NodeStatus } from "@/panels/AgentGraph";

interface Action { title: string; why: string; how: string; priority: 1 | 2 | 3 }
interface Step {
  step: string; status: "running" | "done" | "warn" | "failed"; title?: string; detail?: string; project_id?: string;
  notes?: string[]; node?: string; review?: { summary: string; actions: Action[] };
}

const EXAMPLES = [
  "Victory Day concert at Ramna Park, Dhaka on 16 December at 6 pm for 6,000 people, 5 hours",
  "University convocation at BUET, Dhaka for 2,500 seated guests, 4 hours",
  "Food and music festival for 4,000 people at Hatirjheel, Dhaka, 8 hours with a bar",
  "Tech conference for 900 people in a hall with a balcony, two days",
];

/** Read the Copilot's JSON-lines stream, keeping one row per step (latest status wins). */
async function streamPlan(text: string, onStep: (s: Step) => void, signal: AbortSignal) {
  const res = await fetch("/api/v1/copilot/plan", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }), signal,
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null) as { message?: string } | null;
    throw new Error(body?.message ?? `The planner could not start (${res.status}).`);
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

  const go = async (value: string) => {
    if (value.trim().length < 8 || running) return;
    setOpen(true); setSteps([]); setError(null); setProjectId(null); setRunning(true); setNodes({}); setReview(null);
    abort.current = new AbortController();
    try {
      await streamPlan(value.trim(), (s) => {
        if (s.project_id) setProjectId(s.project_id);
        if (s.node) setNodes((n) => ({ ...n, [s.node!]: s.status }));
        if (s.review) setReview(s.review);
        if (s.step === "error") { setError(s.title ?? "Something went wrong."); return; }
        if (s.step === "finished") return;
        setSteps((prev) => {
          const k = prev.findIndex((p) => p.step === s.step);
          if (k < 0) return [...prev, s];
          const next = prev.slice(); next[k] = { ...prev[k], ...s }; return next;
        });
      }, abort.current.signal);
      void qc.invalidateQueries({ queryKey: ["projects"] });
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <form onSubmit={(e) => { e.preventDefault(); void go(text); }}
            className="flex items-stretch gap-2 rounded-[12px] border border-border bg-surface p-1.5 shadow-[var(--shadow-float)] focus-within:ring-2 focus-within:ring-signal/30">
        <Sparkles className="ml-2 mt-2.5 size-5 shrink-0 text-signal" aria-hidden />
        <textarea aria-label="Describe your event" rows={2} value={text} onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void go(text); } }}
                  placeholder="What, where, when and how many: “Concert at Ramna Park, Dhaka on 16 Dec, 6 pm, 6,000 people, 5 hours”"
                  className="min-h-[52px] flex-1 resize-none bg-transparent px-1 py-2 text-[15px] outline-none placeholder:text-muted" />
        <Button type="submit" variant="primary" size="lg" className="self-end" disabled={text.trim().length < 8 || running}>
          {running ? <Loader2 className="animate-spin" /> : null}Plan it
        </Button>
      </form>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {EXAMPLES.map((ex) => (
          <button key={ex} type="button" onClick={() => setText(ex)}
                  className="max-w-full truncate rounded-full border border-border bg-surface/80 px-2.5 py-1 text-xs text-muted hover:border-border-strong hover:text-ink">
            {ex}
          </button>
        ))}
      </div>

      <Dialog open={open} onOpenChange={(v) => { if (!v) { abort.current?.abort(); setOpen(false); } }}>
        <DialogContent wide className="max-h-[94vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Sparkles className="size-5 text-signal" />Event Copilot</DialogTitle>
            <DialogDescription className="line-clamp-2">“{text.trim()}”</DialogDescription>
          </DialogHeader>
          <div className="flex gap-5">
          <AgentGraph status={nodes} />
          <div className="min-w-0 flex-1">
          <ol className="space-y-3" aria-live="polite">
            {steps.map((s) => (
              <li key={s.step} className="flex gap-3">
                <span className="mt-0.5">
                  {s.status === "running" ? <Loader2 className="size-4 animate-spin text-signal" />
                    : s.status === "done" ? <CheckCircle2 className="size-4 text-egress" />
                    : s.status === "warn" ? <CircleAlert className="size-4 text-caution" />
                    : <XCircle className="size-4 text-danger" />}
                </span>
                <div className="min-w-0">
                  <p className={cn("text-sm", s.status === "running" && "text-muted")}>{s.title}</p>
                  {s.detail && <p className="mt-0.5 text-xs text-muted">{s.detail}</p>}
                </div>
              </li>
            ))}
            {running && steps.length === 0 && <li className="flex gap-3 text-sm text-muted"><Loader2 className="size-4 animate-spin" />Starting…</li>}
          </ol>
          {review && review.actions.length > 0 && (
            <div className="mt-4 rounded-[10px] border border-border p-3">
              <p className="text-sm font-semibold">Safety officer: {review.summary}</p>
              <ol className="mt-2 space-y-2">
                {review.actions.map((a, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <span className={cn("mt-0.5 grid size-5 shrink-0 place-items-center rounded-full text-2xs font-semibold text-white",
                      a.priority === 1 ? "bg-danger" : a.priority === 2 ? "bg-caution" : "bg-line")}>{a.priority}</span>
                    <div><p className="font-medium">{a.title}</p><p className="text-xs text-muted">{a.why} {a.how}</p></div>
                  </li>
                ))}
              </ol>
            </div>
          )}
          </div>
          </div>
          {error && <p className="rounded-[8px] border border-danger/30 bg-danger-soft px-3 py-2 text-sm">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            {running && <Button onClick={() => { abort.current?.abort(); setOpen(false); }}>Cancel</Button>}
            {projectId && (
              <Button variant="primary" onClick={() => { setOpen(false); navigate(`/p/${projectId}?tour=1`); }}>
                Open the plan
              </Button>
            )}
          </div>
          <p className="text-2xs text-muted">The AI reads your request and writes nothing you see as a measurement: sites come from OpenStreetMap, layouts from a solver, numbers from simulation and published planning ratios.</p>
        </DialogContent>
      </Dialog>
    </div>
  );
}
