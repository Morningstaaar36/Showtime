/** Step 1 of the guided journey (route `/`): one question, "Where is your event?", with three
 * big answers: pick it on the map, describe it, or try a sample. Everything else stays out of the way. */
import { ArrowRight, ArrowUpRight, Bot, Building2, ClipboardCheck, Loader2, Map as MapIcon, PencilLine, ShieldCheck, Sparkles, Trees, Users, Wand2 } from "lucide-react";
import type * as React from "react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import { errorText } from "@/api/client";
import { useCreateProject, useDesignVenue, useProjects, useStartAutopilot, useTemplates } from "@/api/queries";
import type { Template } from "@/api/types";
import { VenueThumb } from "@/components/VenueThumb";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { JourneyShell } from "@/journey/JourneyShell";
import { UseCaseGallery } from "@/journey/UseCaseGallery";
import { fmtInt, fmtRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

const EXAMPLES = ["home.example_hall", "home.example_field", "home.example_alley"];

/** The three steps every plan goes through, shown once so a first-time organizer knows what's coming. */
const HOW = [
  { icon: <MapIcon />, tone: "bg-sky-soft text-sky", key: "home.how_1" },
  { icon: <Wand2 />, tone: "bg-signal-soft text-signal", key: "home.how_2" },
  { icon: <ClipboardCheck />, tone: "bg-egress-soft text-egress", key: "home.how_3" },
];

type Way = "describe" | "sample" | null;

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

const ERROR_TOAST_MS = 12_000;

export function HomePage() {
  const templates = useTemplates();
  const projects = useProjects();
  const create = useCreateProject();
  const design = useDesignVenue();
  const autopilot = useStartAutopilot();
  const navigate = useNavigate();
  const [way, setWay] = useState<Way>(null);
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
      // an error stays up long enough to read what to do (the API's hint)
      onError: (e) => toast.error(t("home.design_failed"), { description: `${errorText(e)} ${t("home.try_template")}`, duration: ERROR_TOAST_MS }),
    });
  };
  const busy = design.isPending || (create.isPending && !creating);
  /** Autopilot: the sentence becomes a venue, a test and a plan; the organizer watches it work. */
  const planIt = () => {
    const value = text.trim();
    if (value.length < 10 || busy || autopilot.isPending) return;
    autopilot.mutate({ text: value, depth: "quick" }, {
      onSuccess: (run) => navigate(`/autopilot/${run.id}`),
      onError: (e) => toast.error(t("autopilot.start_failed"), { description: errorText(e), duration: ERROR_TOAST_MS }),
    });
  };
  const working = busy || autopilot.isPending;
  const tooShort = text.trim().length < 10;
  const recent = (projects.data ?? []).slice(0, 6);
  const toggle = (w: Way) => setWay((cur) => (cur === w ? null : w));

  return (
    <JourneyShell step="describe">
      <main id="main" className="bg-hero">
        <div className="mx-auto w-full max-w-6xl space-y-10 px-4 py-10">
          <section className="space-y-5">
            <h1 className="text-balance text-3xl font-bold leading-tight tracking-tight sm:text-4xl">{t("home.title")}</h1>
            <p className="max-w-prose text-lg text-muted">{t("home.lead")}</p>
            <ol className="grid grid-cols-1 gap-3 sm:grid-cols-3" aria-label={t("home.how")}>
              {HOW.map((h, i) => (
                <li key={h.key} className="animate-deal-in relative flex items-center gap-3 rounded-[var(--radius-panel)] border border-border bg-surface/80 p-3 shadow-sm"
                    style={{ animationDelay: `${150 + i * 180}ms` }}>
                  <span className={cn("relative grid size-12 shrink-0 place-items-center rounded-full [&_svg]:size-6", h.tone)}>
                    {h.icon}
                    <span className="absolute -left-1 -top-1 grid size-5 place-items-center rounded-full bg-ink text-2xs font-bold text-plan tabular">{i + 1}</span>
                  </span>
                  <span className="min-w-0">
                    <span className="block font-semibold">{t(h.key)}</span>
                    <span className="block text-xs text-muted">{t(`${h.key}_sub`)}</span>
                  </span>
                  {i < HOW.length - 1 && <span aria-hidden className="animate-flow absolute -right-3 top-1/2 z-10 hidden h-1 w-6 -translate-y-1/2 rounded-full sm:block" />}
                </li>
              ))}
            </ol>
            <Link to="/team" className="inline-flex min-h-11 items-center gap-2 text-sm font-medium text-signal hover:underline">
              <Bot className="size-4" aria-hidden />{t("team.link")}
            </Link>
          </section>

          <section aria-labelledby="where-h" className="space-y-4">
            <h2 id="where-h" className="text-2xl font-bold tracking-tight">{t("home.where")}</h2>
            <div className="grid gap-4 md:grid-cols-3">
              <Link to="/new/place"
                    className="group relative flex min-h-48 flex-col justify-between overflow-hidden rounded-[var(--radius-panel)] bg-[linear-gradient(135deg,var(--sky),var(--signal))] dark:bg-[linear-gradient(135deg,#0b6fa4,#4b3fd6)] p-5 text-white shadow-[var(--shadow-float)] transition hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal">
                <span className="grid size-12 place-items-center rounded-full bg-white/20 [&_svg]:size-6"><MapIcon /></span>
                <span>
                  <span className="block text-xl font-bold">{t("home.way_map")}</span>
                  <span className="mt-1 block text-sm text-white/90">{t("home.way_map_lead")}</span>
                </span>
                <span className="inline-flex items-center gap-1 text-sm font-semibold">{t("home.way_map_go")}<ArrowRight className="size-4 transition group-hover:translate-x-1" /></span>
                <span className="absolute right-3 top-3 rounded-full bg-white/25 px-2.5 py-0.5 text-xs font-semibold">{t("home.recommended")}</span>
              </Link>
              <WayCard active={way === "describe"} onClick={() => toggle("describe")} icon={<PencilLine />} tone="bg-pink-soft text-pink"
                       title={t("home.way_describe")} lead={t("home.way_describe_lead")} />
              <WayCard active={way === "sample"} onClick={() => toggle("sample")} icon={<Sparkles />} tone="bg-orange-soft text-orange"
                       title={t("home.way_sample")} lead={t("home.way_sample_lead")} />
            </div>

            {way === "describe" && (
              <section aria-labelledby="desc-h" className="animate-deal-in rounded-[var(--radius-panel)] border-2 border-pink/30 bg-surface p-5 shadow-sm">
                <h3 id="desc-h" className="text-lg font-semibold">{t("autopilot.describe_title")}</h3>
                <p className="mt-1 text-sm text-muted">{t("autopilot.describe_lead")}</p>
                <form className="mt-3 space-y-3" onSubmit={(e) => { e.preventDefault(); planIt(); }}>
                  <Label htmlFor="venue-text" className="sr-only">{t("autopilot.describe_title")}</Label>
                  <textarea id="venue-text" rows={3} value={text} onChange={(e) => setText(e.target.value)} maxLength={500} autoFocus={!text}
                            placeholder={t("autopilot.describe_ph")}
                            className="w-full resize-y rounded-[var(--radius-control)] border border-border bg-surface px-3 py-2 text-base outline-none placeholder:text-muted/80 focus:border-signal focus:ring-2 focus:ring-signal/20" />
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-muted">{t("home.try")}</span>
                    {EXAMPLES.map((k) => (
                      <button key={k} type="button" onClick={() => setText(t(k))}
                              className="min-h-11 rounded-full bg-pink-soft px-3 text-sm font-medium text-pink hover:brightness-95">
                        {t(`${k}_chip`)}
                      </button>
                    ))}
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <p className="mr-auto text-sm text-muted">{t("autopilot.plan_it_hint")}</p>
                    <Button type="button" size="lg" onClick={fromText} disabled={tooShort || working}>
                      {busy ? <Loader2 className="animate-spin" /> : <PencilLine />}{busy ? t("home.drafting") : t("autopilot.just_draw")}
                    </Button>
                    <Button type="submit" variant="primary" size="lg" disabled={tooShort || working}>
                      {autopilot.isPending ? <Loader2 className="animate-spin" /> : <Wand2 />}{autopilot.isPending ? t("autopilot.starting") : t("autopilot.plan_it")}
                    </Button>
                  </div>
                </form>
              </section>
            )}

            {way === "sample" && (
              <section aria-labelledby="tpl-h" className="animate-deal-in space-y-3">
                <h3 id="tpl-h" className="text-lg font-semibold">{t("home.templates")}</h3>
                {templates.isError ? <ErrorState message={(templates.error as Error).message} onRetry={() => templates.refetch()} /> : (
                  <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {(templates.data ?? [null, null, null, null]).map((tpl, i) => (
                      <li key={tpl?.id ?? i}>
                        {tpl ? (
                          <button type="button" onClick={() => fromTemplate(tpl)} disabled={!!creating}
                                  className="group flex h-full w-full flex-col overflow-hidden rounded-[var(--radius-panel)] border-2 border-transparent bg-surface text-left shadow-sm transition hover:-translate-y-0.5 hover:border-orange focus-visible:outline-2 focus-visible:outline-signal disabled:opacity-60">
                            <span className="block h-28 bg-orange-soft/60 p-2"><VenueThumb venue={tpl.venue} className="size-full" /></span>
                            <span className="flex flex-1 flex-col gap-1 p-3">
                              <span className="flex items-center gap-1.5 font-semibold">
                                {tpl.mode === "outdoor" ? <Trees className="size-4 text-teal" /> : <Building2 className="size-4 text-sky" />}
                                {tpl.name}
                                {creating === tpl.id && <Loader2 className="ml-auto size-4 animate-spin text-signal" />}
                              </span>
                              <span className="line-clamp-2 text-sm text-muted">{tpl.description}</span>
                              <span className="mt-auto flex items-center gap-1 pt-1 text-sm text-muted tabular"><Users className="size-3.5" />{t("ui.home.people", { n: fmtInt(tpl.people) })}</span>
                            </span>
                          </button>
                        ) : <Skeleton className="h-56" />}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}
          </section>

          <UseCaseGallery projects={projects.data} onSample={(id) => navigate(`/p/${id}`)}
                          onDescribe={(value) => {
                            setText(value);
                            setWay("describe");
                            window.setTimeout(() => document.getElementById("desc-h")?.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "center" }), 50);
                          }} />

          <section aria-labelledby="plans-h" className="space-y-3">
            <div className="flex items-baseline justify-between gap-2">
              <h2 id="plans-h" className="text-xl font-bold tracking-tight">{t("home.your_plans")}</h2>
              <Link to="/projects" className="flex min-h-11 items-center gap-1 text-sm font-medium text-signal hover:underline">{t("home.all_plans")}<ArrowUpRight className="size-3.5" /></Link>
            </div>
            {projects.isError ? <ErrorState message={(projects.error as Error).message} hint={(projects.error as { hint?: string }).hint} onRetry={() => projects.refetch()} />
              : projects.isLoading ? <div className="grid gap-3 sm:grid-cols-3"><Skeleton className="h-20" /><Skeleton className="h-20" /><Skeleton className="h-20" /></div>
              : recent.length === 0 ? <EmptyState title={t("home.no_plans")} body={t("home.no_plans_body")} />
              : (
                <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {recent.map((p) => (
                    <li key={p.id}>
                      <Link to={`/p/${p.id}`} className="flex min-h-11 items-center gap-3 rounded-[var(--radius-panel)] border border-border bg-surface p-2.5 shadow-sm transition hover:-translate-y-0.5 hover:border-signal">
                        <span className="h-12 w-16 shrink-0 rounded-[8px] bg-signal-soft p-1">{p.thumb && <VenueThumb venue={p.thumb} className="size-full" />}</span>
                        <span className="min-w-0">
                          <span className="block truncate font-semibold">{p.name}</span>
                          <span className="block text-sm text-muted">{t("ui.home.people_when", { n: fmtInt(p.people), when: fmtRelative(p.updated_at) })}</span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            <p className="flex items-center gap-1.5 text-sm text-muted"><ShieldCheck className="size-4 text-egress" />{t("home.trust")}</p>
          </section>
        </div>
      </main>
    </JourneyShell>
  );
}

function WayCard({ active, onClick, icon, tone, title, lead }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; tone: string; title: string; lead: string;
}) {
  return (
    <button type="button" aria-expanded={active} onClick={onClick}
            className={cn("group flex min-h-48 flex-col justify-between rounded-[var(--radius-panel)] border-2 bg-surface p-5 text-left shadow-sm transition hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal",
              active ? "border-signal" : "border-transparent hover:border-border-strong")}>
      <span className={cn("grid size-12 place-items-center rounded-full [&_svg]:size-6", tone)}>{icon}</span>
      <span>
        <span className="block text-xl font-bold">{title}</span>
        <span className="mt-1 block text-sm text-muted">{lead}</span>
      </span>
      <span className="inline-flex items-center gap-1 text-sm font-semibold text-signal">{active ? t("home.way_hide") : t("home.way_open")}<ArrowRight className={cn("size-4 transition", active ? "rotate-90" : "group-hover:translate-x-1")} /></span>
    </button>
  );
}
