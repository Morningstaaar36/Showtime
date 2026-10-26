import { Loader2, Sparkles } from "lucide-react";
import { useState } from "react";
import { useDesignVenue } from "@/api/queries";
import type { VenueDraft } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/input";
import { ErrorState } from "@/components/ui/states";
import { DraftPreview } from "./DraftPreview";
import { t, tItems } from "@/i18n";


/** "Describe it": the designer agent writes the layout, the solver builds it, the checks run. */
export function DescribeTab({ onDraft }: { onDraft: (d: VenueDraft | null) => void }) {
  const design = useDesignVenue();
  const [text, setText] = useState("");
  const run = (value: string) => design.mutate(value, { onSuccess: (d) => onDraft(d.venue ? d : null) });
  return (
    <div className="space-y-3">
      <div className="grid gap-1.5">
        <Label htmlFor="describe">{t("ui.describetab.describe_the_venue")}</Label>
        <textarea
          id="describe"
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && text.trim().length >= 10) run(text); }}
          placeholder={t("ui.describetab.size_indoor_or_open_air")}
          className="w-full resize-y rounded-[var(--radius-control)] border border-border bg-surface px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-signal/40"
        />
        <div className="flex flex-wrap gap-1.5">
          {tItems("ui.describetab.examples").map((ex) => (
            <button key={ex.label} type="button" onClick={() => setText(ex.text)}
                    className="rounded-full border border-border px-2.5 py-1 text-left text-xs text-muted hover:border-border-strong hover:text-ink">
              {ex.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Button variant="primary" disabled={text.trim().length < 10 || design.isPending} onClick={() => run(text)}>
          {design.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
          {design.isPending ? t("ui.describetab.designing") : design.data ? t("ui.describetab.design_again") : t("ui.describetab.design_venue")}
        </Button>
        <p className="text-xs text-muted">
          {design.isPending
            ? t("ui.describetab.the_ai_writes_the_layout")
            : t("ui.describetab.the_ai_chooses_sizes_and")}
        </p>
      </div>
      {design.isError && (
        <ErrorState title={t("ui.describetab.the_venue_couldnt_be_designed")} message={(design.error as Error).message}
                    hint={(design.error as { hint?: string }).hint} onRetry={() => run(text)} />
      )}
      {design.data && !design.data.venue && (
        <ErrorState title={t("ui.describetab.no_layout_came_back")} message={design.data.problems.join(" ") || t("ui.describetab.try_describing_it_in_more")} />
      )}
      {design.data?.venue && <DraftPreview draft={design.data} />}
    </div>
  );
}
