/** How the AI designed a venue from words: each design round (what the plan checker measured,
 * what the plan critic saw, the instant estimate), which round was kept, and the real building
 * the map found. Read from venue.extensions.generated (api/agents/venue_designer.py). */
import { CheckCircle2, Eye, MapPin, PencilRuler, TriangleAlert } from "lucide-react";
import type { Venue } from "@/api/types";
import { t } from "@/i18n";
import { fmtDuration, fmtInt } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface DesignRound {
  round: number;
  summary: string;
  problems: string[];
  fixes: string[];
  notes: string[];
  critic: "off" | "ok" | "issues" | "no answer";
  critique: string[];
  evac_s: number | null;
  not_out: number;
  kept?: boolean;
}

interface Site { source: string; width_m: number | null; depth_m: number | null; notes?: string[] }

export function designOf(venue: Venue | undefined): { rounds: DesignRound[]; site: Site | null } {
  const gen = (venue?.extensions as Record<string, unknown> | undefined)?.generated as
    { design_rounds?: DesignRound[]; site?: Site } | undefined;
  return { rounds: Array.isArray(gen?.design_rounds) ? gen.design_rounds : [], site: gen?.site ?? null };
}

export function DesignRounds({ venue, className }: { venue: Venue | undefined; className?: string }) {
  const { rounds, site } = designOf(venue);
  if (rounds.length === 0) return null;
  const kept = rounds.find((r) => r.kept) ?? rounds[rounds.length - 1];
  return (
    <details className={cn("rounded-[10px] border border-border", className)} data-testid="design-rounds">
      <summary className="flex min-h-11 cursor-pointer items-center gap-2 px-3 text-sm font-semibold">
        <PencilRuler className="size-4 text-muted" aria-hidden />
        {t("design.title")}
        <span className="ml-auto text-xs font-normal text-muted">
          {t("design.rounds_kept", { n: rounds.length, kept: kept.round })}
        </span>
      </summary>
      <div className="space-y-3 border-t border-border p-3 text-sm">
        <p className="text-muted">{t("design.lead")}</p>
        {site && (
          <p className="flex items-start gap-1.5">
            <MapPin className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
            <span>
              {site.width_m && site.depth_m
                ? t("design.site_found", { source: site.source, w: fmtInt(site.width_m), d: fmtInt(site.depth_m) })
                : t("design.site_none")}
              {site.notes?.length ? <span className="block text-xs text-muted">{site.notes.join(" ")}</span> : null}
            </span>
          </p>
        )}
        <ol className="space-y-2">
          {rounds.map((r) => (
            <li key={r.round} className={cn("rounded-[8px] border p-2.5", r.kept ? "border-signal bg-signal-soft/40" : "border-border")}>
              <p className="flex flex-wrap items-center gap-x-2 font-medium">
                {t("design.round", { n: r.round })}
                {r.kept && <span className="inline-flex items-center gap-1 text-xs text-signal"><CheckCircle2 className="size-3.5" aria-hidden />{t("design.kept")}</span>}
                {r.evac_s != null && (
                  <span className="ml-auto text-xs font-normal text-muted tabular">{t("design.estimate", { t: fmtDuration(r.evac_s) })}</span>
                )}
              </p>
              <p className="mt-0.5 text-xs text-muted">{r.summary}</p>
              {[...r.problems, ...r.fixes].length > 0 && (
                <ul className="mt-1.5 space-y-1" aria-label={t("design.to_fix")}>
                  {[...r.problems, ...r.fixes].map((f, i) => (
                    <li key={i} className="flex items-start gap-1.5"><TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-caution" aria-hidden /><span>{f}</span></li>
                  ))}
                </ul>
              )}
              {r.critique.length > 0 && (
                <ul className="mt-1.5 space-y-1" aria-label={t("design.critic")}>
                  {r.critique.map((c, i) => (
                    <li key={i} className="flex items-start gap-1.5"><Eye className="mt-0.5 size-3.5 shrink-0 text-muted" aria-hidden /><span>{c}</span></li>
                  ))}
                </ul>
              )}
              {[...r.problems, ...r.fixes, ...r.critique].length === 0 && (
                <p className="mt-1 text-xs text-egress">{t("design.clean")}</p>
              )}
              <p className="mt-1 text-2xs text-muted">{t(`design.critic_${r.critic.replace(" ", "_")}`)}</p>
            </li>
          ))}
        </ol>
        {kept.notes.length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted">{t("design.code_notes")}</p>
            <ul className="mt-1 space-y-1">
              {kept.notes.map((n, i) => <li key={i} className="text-sm">{n}</li>)}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}
