import { AlertTriangle, CheckCircle2, Info, Layers, Users } from "lucide-react";
import type { Pt, VenueDraft } from "@/api/types";
import { VenueThumb } from "@/components/VenueThumb";
import { Badge } from "@/components/ui/badge";
import { bbox } from "@/scene/geom";
import { fmtInt } from "@/lib/format";

/** What a generated venue looks like before it becomes a project: plan, numbers, what was assumed. */
export function DraftPreview({ draft }: { draft: VenueDraft }) {
  const v = draft.venue;
  if (!v) return null;
  const [x0, y0, x1, y1] = bbox(v.floors.flatMap((f) => f.walkable as Pt[]));
  const people = v.floors.reduce((n, f) => n + f.zones.reduce((m, z) => m + z.people, 0), 0);
  const exits = v.floors.reduce((n, f) => n + f.exits.length, 0);
  const errors = (draft.checks ?? []).filter((c) => c.severity === "error");
  const warnings = (draft.checks ?? []).filter((c) => c.severity === "warning");
  return (
    <div className="grid gap-4 rounded-[10px] border border-border bg-surface p-3 md:grid-cols-[1.1fr_1fr]">
      <div className="grid gap-2">
        {v.floors.map((f) => (
          <div key={f.floor_id} className="rounded-[6px] bg-plan p-2">
            {v.floors.length > 1 && <p className="mb-1 text-2xs font-medium text-muted">{f.name ?? f.floor_id}</p>}
            <VenueThumb venue={v} floor={f.floor_id} className={v.floors.length > 1 ? "h-36 w-full" : "h-56 w-full"} />
          </div>
        ))}
      </div>
      <div className="min-w-0 space-y-3 text-sm">
        <div>
          <p className="font-semibold">{v.name}</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <Badge tone="outline">{v.mode === "indoor" ? "Indoor" : "Open-air"}</Badge>
            <Badge tone="neutral" className="tabular">{fmtInt(x1 - x0)} × {fmtInt(y1 - y0)} m</Badge>
            <Badge tone="neutral"><Users />{fmtInt(people)}</Badge>
            <Badge tone="neutral">{exits} exits</Badge>
            {v.floors.length > 1 && <Badge tone="neutral"><Layers />{v.floors.length} floors</Badge>}
          </div>
        </div>
        {errors.length === 0 ? (
          <p className="flex items-start gap-1.5 text-egress"><CheckCircle2 className="mt-0.5 size-4 shrink-0" />
            Passes the geometry checks: every crowd area reaches an exit.</p>
        ) : (
          <ul className="space-y-1">
            {errors.map((c, i) => (
              <li key={i} className="flex items-start gap-1.5 text-danger"><AlertTriangle className="mt-0.5 size-4 shrink-0" />
                <span>{c.message}{c.hint ? <span className="text-muted"> {c.hint}</span> : null}</span></li>
            ))}
            <li className="text-xs text-muted">You can still create it and fix these in the editor.</li>
          </ul>
        )}
        {[...draft.problems, ...warnings.map((w) => w.message)].length > 0 && (
          <ul className="space-y-1">
            {[...draft.problems, ...warnings.map((w) => w.message)].slice(0, 4).map((p, i) => (
              <li key={i} className="flex items-start gap-1.5 text-caution"><AlertTriangle className="mt-0.5 size-4 shrink-0" /><span className="text-ink">{p}</span></li>
            ))}
          </ul>
        )}
        {[...draft.assumptions, ...draft.notes].length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted">Assumed or adjusted</p>
            <ul className="mt-1 space-y-1">
              {[...draft.assumptions, ...draft.notes].slice(0, 7).map((a, i) => (
                <li key={i} className="flex items-start gap-1.5"><Info className="mt-0.5 size-3.5 shrink-0 text-muted" /><span>{a}</span></li>
              ))}
            </ul>
          </div>
        )}
        {(draft.model || draft.attribution) && (
          <p className="text-2xs text-muted">{draft.model ? `Layout by ${draft.model}; geometry solved and checked in code.` : draft.attribution}</p>
        )}
      </div>
    </div>
  );
}
