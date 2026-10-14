/** Step 1 of the guided journey (route `/`): pick a template or describe the venue. */
import { ArrowUpRight, Building2, Loader2, Sparkles, Trees, Users } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import { useCreateProject, useDesignVenue, useProjects, useTemplates } from "@/api/queries";
import type { Template } from "@/api/types";
import { VenueThumb } from "@/components/VenueThumb";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { JourneyShell } from "@/journey/JourneyShell";
import { fmtInt, fmtRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

const EXAMPLES = ["home.example_hall", "home.example_field", "home.example_alley"];

export function HomePage() {
  const templates = useTemplates();
  const projects = useProjects();
  const create = useCreateProject();
  const design = useDesignVenue();
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [creating, setCreating] = useState<string | null>(null);

  const open = (id: string) => navigate(`/p/${id}/describe`);
  const fromTemplate = (tpl: Template) => {
    setCreating(tpl.id);
    create.mutate({ name: tpl.name, template_id: tpl.id }, {
      onSuccess: (p) => open(p.id),
      onError: (e) => toast.error(e.message),
      onSettled: () => setCreating(null),
    });
  };
  const fromText = () => {
    const value = text.trim();
    if (value.length < 10 || design.isPending) return;
    design.mutate(value, {
      onSuccess: (d) => {
        if (!d.venue) {
          toast.error(t("home.design_failed"), { description: d.problems[0] ?? t("home.try_template") });
          return;
        }
        create.mutate({ name: d.venue.name, venue: d.venue, description: value }, {
          onSuccess: (p) => open(p.id),
          onError: (e) => toast.error(e.message),
        });
      },
      onError: (e) => toast.error(t("home.design_failed"), { description: `${e.message} ${t("home.try_template")}` }),
    });
  };
  const busy = design.isPending || (create.isPending && !creating);
  const recent = (projects.data ?? []).slice(0, 6);

  return (
    <JourneyShell step="describe">
      <main id="main" className="mx-auto w-full max-w-6xl space-y-10 px-4 py-8">
        <section>
          <h1 className="text-balance text-3xl font-semibold leading-tight tracking-tight">{t("home.title")}</h1>
          <p className="mt-2 max-w-prose text-base text-muted">{t("home.lead")}</p>
        </section>

        <section aria-labelledby="tpl-h" className="space-y-3">
          <h2 id="tpl-h" className="text-lg font-semibold">{t("home.templates")}</h2>
          {templates.isError ? <ErrorState message={(templates.error as Error).message} onRetry={() => templates.refetch()} /> : (
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {(templates.data ?? [null, null, null, null]).map((tpl, i) => (
                <li key={tpl?.id ?? i}>
                  {tpl ? (
                    <button type="button" onClick={() => fromTemplate(tpl)} disabled={!!creating}
                            className="group flex h-full w-full flex-col overflow-hidden rounded-[10px] border border-border bg-surface text-left transition hover:border-signal focus-visible:outline-2 focus-visible:outline-signal disabled:opacity-60">
                      <span className="block h-28 bg-plan p-2"><VenueThumb venue={tpl.venue} className="size-full" /></span>
                      <span className="flex flex-1 flex-col gap-1 p-3">
                        <span className="flex items-center gap-1.5 font-medium">
                          {tpl.mode === "outdoor" ? <Trees className="size-4 text-muted" /> : <Building2 className="size-4 text-muted" />}
                          {tpl.name}
                          {creating === tpl.id && <Loader2 className="ml-auto size-4 animate-spin text-signal" />}
                        </span>
                        <span className="line-clamp-2 text-sm text-muted">{tpl.description}</span>
                        <span className="mt-auto flex items-center gap-1 pt-1 text-sm text-muted tabular"><Users className="size-3.5" />{fmtInt(tpl.people)} people</span>
                      </span>
                    </button>
                  ) : <Skeleton className="h-56" />}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="desc-h" className="rounded-[14px] border border-border bg-surface p-5">
          <h2 id="desc-h" className="text-lg font-semibold">{t("home.describe")}</h2>
          <p className="mt-1 text-sm text-muted">{t("home.describe_lead")}</p>
          <form className="mt-3 space-y-3" onSubmit={(e) => { e.preventDefault(); fromText(); }}>
            <Label htmlFor="venue-text" className="sr-only">{t("home.describe")}</Label>
            <textarea id="venue-text" rows={3} value={text} onChange={(e) => setText(e.target.value)} maxLength={500}
                      placeholder={t("home.describe_ph")}
                      className="w-full resize-y rounded-[var(--radius-control)] border border-border bg-surface px-3 py-2 text-base outline-none placeholder:text-muted/80 focus:border-signal focus:ring-2 focus:ring-signal/20" />
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-muted">{t("home.try")}</span>
              {EXAMPLES.map((k) => (
                <button key={k} type="button" onClick={() => setText(t(k))}
                        className="min-h-11 rounded-full border border-border px-3 text-sm text-muted hover:border-border-strong hover:text-ink">
                  {t(`${k}_chip`)}
                </button>
              ))}
              <Button type="submit" variant="primary" size="lg" className="ml-auto" disabled={text.trim().length < 10 || busy}>
                {busy ? <Loader2 className="animate-spin" /> : <Sparkles />}{busy ? t("home.drafting") : t("home.draft")}
              </Button>
            </div>
          </form>
        </section>

        <section aria-labelledby="plans-h" className="space-y-3">
          <div className="flex items-baseline justify-between gap-2">
            <h2 id="plans-h" className="text-lg font-semibold">{t("home.your_plans")}</h2>
            <Link to="/projects" className="flex min-h-11 items-center gap-1 text-sm text-signal hover:underline">{t("home.all_plans")}<ArrowUpRight className="size-3.5" /></Link>
          </div>
          {projects.isError ? <ErrorState message={(projects.error as Error).message} hint={(projects.error as { hint?: string }).hint} onRetry={() => projects.refetch()} />
            : projects.isLoading ? <div className="grid gap-3 sm:grid-cols-3"><Skeleton className="h-20" /><Skeleton className="h-20" /><Skeleton className="h-20" /></div>
            : recent.length === 0 ? <EmptyState title={t("home.no_plans")} body={t("home.no_plans_body")} />
            : (
              <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {recent.map((p) => (
                  <li key={p.id}>
                    <Link to={`/p/${p.id}`} className={cn("flex min-h-11 items-center gap-3 rounded-[10px] border border-border bg-surface p-2.5 hover:border-border-strong")}>
                      <span className="h-12 w-16 shrink-0 rounded-[6px] bg-plan p-1">{p.thumb && <VenueThumb venue={p.thumb} className="size-full" />}</span>
                      <span className="min-w-0">
                        <span className="block truncate font-medium">{p.name}</span>
                        <span className="block text-sm text-muted">{fmtInt(p.people)} people · {fmtRelative(p.updated_at)}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          <p className="text-sm text-muted">{t("home.more_ways")} <Link to="/projects" className="text-signal hover:underline">{t("home.more_ways_link")}</Link></p>
        </section>
      </main>
    </JourneyShell>
  );
}
