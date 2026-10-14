import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { PanelTitle } from "@/components/ui/misc";
import { cn } from "@/lib/utils";

interface Review { summary: string; actions: { title: string; why: string; how: string; priority: 1 | 2 | 3 }[] }

/** The safety officer agent's prioritised actions for this plan (numbers checked against results). */
export function OfficerCard({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["review", projectId], queryFn: () => api.get<Review>(`/projects/${projectId}/review`) });
  const run = useMutation({
    mutationFn: () => api.post<Review>(`/projects/${projectId}/review`),
    onSuccess: (r) => qc.setQueryData(["review", projectId], r),
    onError: (e) => toast.error(e.message),
  });
  const r = q.data;
  return (
    <section className="space-y-2" aria-label="Safety officer">
      <div className="flex items-center justify-between">
        <PanelTitle><ShieldCheck className="mr-1.5 inline size-4 text-signal" />Safety officer</PanelTitle>
        <Button size="sm" variant="ghost" disabled={run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? <Loader2 className="animate-spin" /> : null}{r?.actions.length ? "Review again" : "Review my plan"}
        </Button>
      </div>
      {r?.summary && <p className="text-xs text-muted">{r.summary}</p>}
      {r && r.actions.length > 0 ? (
        <ol className="space-y-2">
          {r.actions.map((a, i) => (
            <li key={i} className="flex gap-2 rounded-[var(--radius-control)] border border-border p-2">
              <span className={cn("mt-0.5 grid size-6 shrink-0 place-items-center rounded-full text-xs font-bold tabular",
                a.priority === 1 ? "bg-danger-soft text-danger" : a.priority === 2 ? "bg-caution-soft text-caution" : "bg-surface-3 text-muted")} title={`Priority ${a.priority}`}>{a.priority}</span>
              <div className="min-w-0 text-sm"><p className="font-medium">{a.title}</p><p className="text-xs text-muted">{a.why}</p><p className="text-xs">{a.how}</p></div>
            </li>
          ))}
        </ol>
      ) : !run.isPending && <p className="text-xs text-muted">An AI safety officer reads the estimates, checks and what-if results and lists what to fix first. Every number it quotes is checked.</p>}
    </section>
  );
}
