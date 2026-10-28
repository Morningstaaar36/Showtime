/** A cited source with where it came from: the incident dataset or a live web search. */
import { Database, ExternalLink, Globe } from "lucide-react";
import { t } from "@/i18n";
import { withYear } from "@/journey/plan/evidence";
import { cn } from "@/lib/utils";

function OriginBadge({ origin, className }: { origin?: string | null; className?: string }) {
  const web = origin === "tavily";
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-2xs font-medium",
                        web ? "bg-sky-soft text-sky" : "bg-surface-3 text-muted", className)} data-testid="origin-badge">
      {web ? <Globe className="size-3" aria-hidden /> : <Database className="size-3" aria-hidden />}
      {t(web ? "evidence_panel.origin_web" : "evidence_panel.origin_dataset")}
    </span>
  );
}

export function SourceLink({ source, className }: {
  source: { incident: string; year?: number | null; source_url: string; origin?: string | null } | null | undefined;
  className?: string;
}) {
  if (!source?.source_url) return null;
  return (
    <span className={cn("flex min-w-0 items-center gap-1.5", className)}>
      <a href={source.source_url} target="_blank" rel="noreferrer" className="flex min-h-11 min-w-0 items-center gap-1 text-xs text-signal hover:underline">
        <ExternalLink className="size-3 shrink-0" aria-hidden />
        <span className="truncate">{t("work.inspired_by", { what: withYear(source.incident, source.year) })}</span>
      </a>
      <OriginBadge origin={source.origin} />
    </span>
  );
}
