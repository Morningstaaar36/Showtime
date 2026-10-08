import { Loader2, Sparkles } from "lucide-react";
import { useState } from "react";
import { useDesignVenue } from "@/api/queries";
import type { VenueDraft } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/input";
import { ErrorState } from "@/components/ui/states";
import { DraftPreview } from "./DraftPreview";

const EXAMPLES = [
  "A two-storey conference hall 45 × 30 m for 1,500 people: stage on the north wall, two 3 m doors on the south, a fire exit east, and a 350-seat balcony along the south wall.",
  "Open-air concert on a 150 × 90 m field in Chattogram for 9,000 people, stage on the east with a crowd barrier, four gates on the west and one on the north, two bars and toilets at the back.",
  "A wedding hall for 300 guests with one main door and a small stage.",
];

/** "Describe it": the designer agent writes the layout, the solver builds it, the checks run. */
export function DescribeTab({ onDraft }: { onDraft: (d: VenueDraft | null) => void }) {
  const design = useDesignVenue();
  const [text, setText] = useState("");
  const run = (value: string) => design.mutate(value, { onSuccess: (d) => onDraft(d.venue ? d : null) });
  return (
    <div className="space-y-3">
      <div className="grid gap-1.5">
        <Label htmlFor="describe">Describe the venue</Label>
        <textarea
          id="describe"
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && text.trim().length >= 10) run(text); }}
          placeholder="Size, indoor or open-air, how many people, where the stage and the doors or gates are, bars, a balcony…"
          className="w-full resize-y rounded-[var(--radius-control)] border border-border bg-surface px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-signal/40"
        />
        <div className="flex flex-wrap gap-1.5">
          {EXAMPLES.map((ex, i) => (
            <button key={i} type="button" onClick={() => setText(ex)}
                    className="rounded-full border border-border px-2.5 py-1 text-left text-xs text-muted hover:border-border-strong hover:text-ink">
              {["Two-floor conference hall", "Open-air concert", "Wedding hall"][i]}
            </button>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Button variant="primary" disabled={text.trim().length < 10 || design.isPending} onClick={() => run(text)}>
          {design.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
          {design.isPending ? "Designing…" : design.data ? "Design again" : "Design venue"}
        </Button>
        <p className="text-xs text-muted">
          {design.isPending
            ? "The AI writes the layout, then code places every wall, exit and zone and checks it."
            : "The AI chooses sizes and positions; exact geometry is computed and checked in code."}
        </p>
      </div>
      {design.isError && (
        <ErrorState title="The venue couldn't be designed" message={(design.error as Error).message}
                    hint={(design.error as { hint?: string }).hint} onRetry={() => run(text)} />
      )}
      {design.data && !design.data.venue && (
        <ErrorState title="No layout came back" message={design.data.problems.join(" ") || "Try describing it in more detail."} />
      )}
      {design.data?.venue && <DraftPreview draft={design.data} />}
    </div>
  );
}
