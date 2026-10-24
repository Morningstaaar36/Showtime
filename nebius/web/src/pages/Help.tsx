/** Help (route `/help`): organizer first. How it works in three steps, what the numbers mean,
 * how good the simulator is against a real experiment, the limits, a plain glossary and the
 * keyboard shortcuts; technical details stay one click away. */
import { ChevronDown, ClipboardCheck, Clock, Gauge, Map as MapIcon, ShieldCheck, Timer, Users, Wand2 } from "lucide-react";
import type * as React from "react";
import { Link } from "react-router";
import { useGlossary, useValidation } from "@/api/queries";
import type { SimulatorValidation } from "@/api/types";
import { AppShell } from "@/app/AppHeader";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/misc";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { ValidationChart, ValidationTable } from "@/panels/ValidationChart";

const STEPS = [
  { icon: <MapIcon />, tone: "bg-sky-soft text-sky", key: "step1" },
  { icon: <Wand2 />, tone: "bg-signal-soft text-signal", key: "step2" },
  { icon: <ClipboardCheck />, tone: "bg-egress-soft text-egress", key: "step3" },
];

/** The numbers an organizer meets on Your plan, each with its own colour. */
const NUMBERS = [
  { icon: <Timer />, tone: "border-t-sky", key: "n_evac" },
  { icon: <Users />, tone: "border-t-pink", key: "n_density" },
  { icon: <Clock />, tone: "border-t-orange", key: "n_latest" },
  { icon: <Gauge />, tone: "border-t-teal", key: "n_capacity" },
];

/** How sure a number is, from quickest to most certain. */
const LEVELS = ["instant", "quick", "full"];

const GLOSSARY = ["people_per_m2", "evac", "peak", "latest", "capacity", "stress_test", "red_team", "fix", "blocked_exit",
  "hotspot", "counterflow", "reaction", "margin", "planning_aid"];

const LIMITS = ["limit_signoff", "limit_pushing", "limit_stairs", "limit_weather", "limit_samples"];

const SHORTCUTS: [string[], string][] = [
  [["Ctrl", "Z"], "sc_undo"], [["Ctrl", "Shift", "Z"], "sc_redo"], [["Space"], "sc_play"],
  [["R"], "sc_stress"], [["/"], "sc_type"], [["V"], "sc_select"], [["E"], "sc_exit"],
  [["B"], "sc_barrier"], [["Z"], "sc_zone"], [["M"], "sc_measure"], [["X"], "sc_block"], [["Esc"], "sc_cancel"],
  [["W"], "sc_wall"], [["D"], "sc_door"], [["O"], "sc_room"], [["S"], "sc_stair"], [["P"], "sc_route"],
  [["Enter"], "sc_finish"], [["Backspace"], "sc_undo_point"],
  [["1"], "sc_plan"], [["2"], "sc_simulate"], [["3"], "sc_redteam"], [["4"], "sc_report"],
];

const TECH = ["tech_instant", "tech_sim", "tech_density", "tech_evac", "tech_wind", "tech_latest"];

const SECTIONS = ["how", "numbers", "verdict", "validation", "limits", "glossary", "shortcuts"];
const sectionLabel = (s: string) => (s === "validation" ? t("validation.nav") : t(`help.${s}`));

/** The verdict headline (what the numbers show) and the badge next to it (how sure they are). */
const VERDICT_TERMS = [
  ["v_holds", "border-t-egress"], ["v_at_risk", "border-t-caution"], ["v_fails", "border-t-danger"],
  ["v_confirmed", "border-t-egress"], ["v_partly", "border-t-caution"], ["v_unconfirmed", "border-t-line"], ["v_failed", "border-t-danger"],
] as const;

const VALIDATION_LIMITS = ["limit_forces", "limit_motivation", "limit_density", "limit_scope"];

export function HelpPage() {
  const glossary = useGlossary();
  const validation = useValidation();
  return (
    <AppShell className="bg-hero">
      <div className="mx-auto w-full max-w-5xl space-y-12 px-4 py-10">
        <div>
          <h1 className="text-3xl font-bold leading-tight tracking-tight sm:text-4xl">{t("help.title")}</h1>
          <p className="mt-2 max-w-prose text-lg text-muted">{t("help.lead")}</p>
          <Link to="/team" className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-signal hover:underline">{t("team.link")}</Link>
          <nav aria-label={t("help.on_this_page")} className="mt-5 flex flex-wrap gap-2">
            {SECTIONS.map((s) => (
              <a key={s} href={`#${s}`} className="inline-flex min-h-11 items-center rounded-full border border-border bg-surface px-4 text-sm font-medium shadow-sm hover:border-signal hover:text-signal">
                {sectionLabel(s)}
              </a>
            ))}
          </nav>
        </div>

        <Section id="how" title={t("help.how")} lead={t("help.how_lead")}>
          <ol className="grid gap-4 md:grid-cols-3">
            {STEPS.map((s, i) => (
              <li key={s.key} className="rounded-[var(--radius-panel)] border border-border bg-surface p-5 shadow-sm">
                <span className={cn("grid size-11 place-items-center rounded-full [&_svg]:size-5", s.tone)} aria-hidden>{s.icon}</span>
                <p className="mt-3 text-sm font-semibold text-muted">{t("help.step_n", { n: i + 1 })}</p>
                <h3 className="text-lg font-bold">{t(`help.${s.key}`)}</h3>
                <p className="mt-1 text-muted">{t(`help.${s.key}_body`)}</p>
              </li>
            ))}
          </ol>
          <Button asChild variant="primary" size="lg" className="mt-5"><Link to="/">{t("help.start")}</Link></Button>
        </Section>

        <Section id="verdict" title={t("help.verdict")} lead={t("help.verdict_lead")}>
          <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {VERDICT_TERMS.map(([k, tone]) => (
              <div key={k} className={cn("rounded-[var(--radius-panel)] border border-t-4 border-border bg-surface p-4 shadow-sm", tone)}>
                <dt className="font-bold">{t(`help.${k}`)}</dt>
                <dd className="mt-1 text-sm text-muted">{t(`help.${k}_body`)}</dd>
              </div>
            ))}
          </dl>
        </Section>

        <Section id="numbers" title={t("help.numbers_title")} lead={t("help.numbers_lead")}>
          <dl className="grid gap-4 sm:grid-cols-2">
            {NUMBERS.map((n) => (
              <div key={n.key} className={cn("rounded-[var(--radius-panel)] border border-t-4 border-border bg-surface p-5 shadow-sm", n.tone)}>
                <dt className="flex items-center gap-2 text-lg font-bold [&_svg]:size-5 [&_svg]:text-muted">{n.icon}{t(`help.${n.key}`)}</dt>
                <dd className="mt-1 text-muted">{t(`help.${n.key}_body`)}</dd>
              </div>
            ))}
          </dl>
          <h3 className="mt-8 text-lg font-bold">{t("help.levels")}</h3>
          <p className="mt-1 max-w-prose text-muted">{t("help.levels_lead")}</p>
          <ol className="mt-4 grid gap-3 md:grid-cols-3">
            {LEVELS.map((l, i) => (
              <li key={l} className="rounded-[var(--radius-panel)] border border-border bg-surface p-4">
                <p className="flex items-center gap-2 font-semibold">
                  <span aria-hidden className="flex gap-0.5">{LEVELS.map((_, k) => <span key={k} className={cn("h-2 w-4 rounded-full", k <= i ? "bg-signal" : "bg-surface-3")} />)}</span>
                  {t(`help.level_${l}`)}
                </p>
                <p className="mt-1 text-sm text-muted">{t(`help.level_${l}_body`)}</p>
              </li>
            ))}
          </ol>
        </Section>

        <Section id="validation" title={t("validation.title")} lead={t("validation.lead")}>
          {validation.data ? <SimulatorCheck data={validation.data} /> : validation.isError && (
            <p className="rounded-[var(--radius-panel)] border border-border bg-surface p-5 text-muted">{t("validation.missing")}</p>
          )}
        </Section>

        <Section id="limits" title={t("help.limits")}>
          <div className="rounded-[var(--radius-panel)] border-2 border-caution/40 bg-caution-soft/60 p-5">
            <p className="flex items-center gap-2 text-lg font-bold"><ShieldCheck className="size-5 shrink-0 text-caution" aria-hidden />{t("app.disclaimer")}</p>
            <ul className="mt-3 list-disc space-y-1.5 pl-6">
              {LIMITS.map((k) => <li key={k}>{t(`help.${k}`)}</li>)}
            </ul>
          </div>
        </Section>

        <Section id="glossary" title={t("help.glossary")} lead={t("help.glossary_lead")}>
          <dl className="grid gap-x-8 gap-y-4 rounded-[var(--radius-panel)] border border-border bg-surface p-5 shadow-sm sm:grid-cols-2">
            {GLOSSARY.map((g) => (
              <div key={g}>
                <dt className="font-semibold">{t(`help.g_${g}`)}</dt>
                <dd className="mt-0.5 text-sm text-muted">{t(`help.g_${g}_body`)}</dd>
              </div>
            ))}
          </dl>
        </Section>

        <Section id="shortcuts" title={t("help.shortcuts")} lead={t("help.shortcuts_lead")}>
          <ul className="grid gap-x-8 rounded-[var(--radius-panel)] border border-border bg-surface px-5 py-2 shadow-sm sm:grid-cols-2">
            {SHORTCUTS.map(([keys, key]) => (
              <li key={key} className="flex min-h-11 items-center justify-between gap-3 border-b border-border py-1.5 text-sm">
                <span>{t(`help.${key}`)}</span>
                <span className="flex gap-1">{keys.map((k) => <Kbd key={k}>{k}</Kbd>)}</span>
              </li>
            ))}
          </ul>
        </Section>

        <details className="group rounded-[var(--radius-panel)] border border-border bg-surface shadow-sm">
          <summary className="flex min-h-14 cursor-pointer list-none items-center gap-3 px-5 py-3">
            <span className="min-w-0 flex-1">
              <span className="block text-lg font-bold">{t("help.tech")}</span>
              <span className="block text-sm text-muted">{t("help.tech_lead")}</span>
            </span>
            <ChevronDown className="size-5 shrink-0 text-muted transition group-open:rotate-180" aria-hidden />
          </summary>
          <div className="space-y-8 border-t border-border p-5">
            <dl className="space-y-4">
              {TECH.map((k) => (
                <div key={k} className="max-w-prose">
                  <dt className="font-semibold">{t(`help.${k}`)}</dt>
                  <dd className="mt-0.5 text-sm text-muted">{t(`help.${k}_body`)}</dd>
                </div>
              ))}
            </dl>
            {(glossary.data ?? []).length > 0 && (
              <div>
                <h3 className="font-semibold">{t("help.tech_glossary")}</h3>
                <dl className="mt-3 grid gap-x-8 gap-y-3 sm:grid-cols-2">
                  {(glossary.data ?? []).map((g) => (
                    <div key={g.term}>
                      <dt className="text-sm font-medium">{g.term}</dt>
                      <dd className="text-sm text-muted">{g.definition}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
          </div>
        </details>
      </div>
    </AppShell>
  );
}

/** "How good is the simulator?": the measured-vs-simulated chart, the error in words, the limits. */
export function SimulatorCheck({ data, chartWidth }: { data: SimulatorValidation; chartWidth?: number }) {
  const widths = data.widths.map((w) => w.b_m);
  const median = data.median_abs_error_pct.toFixed(0);
  const n = data.widths.length;
  const close = data.median_abs_error_pct < 10;
  const lower = data.mean_error_pct < 0;
  const verdict = close ? "verdict_close" : lower ? "verdict_lower" : "verdict_higher";
  return (
    <div className="space-y-5">
      <p className="max-w-prose text-muted">
        {t("validation.what", { n, min: Math.min(...widths).toFixed(1), max: Math.max(...widths).toFixed(1), seeds: data.meta.seeds.length })}
      </p>
      <div className="rounded-[var(--radius-panel)] border border-border bg-surface p-5 shadow-sm">
        <p className="text-lg font-bold" data-testid="validation-verdict">{t(`validation.${verdict}`, { median, n })}</p>
        <div className="mt-4"><ValidationChart data={data} width={chartWidth} /></div>
        <details className="mt-3">
          <summary className="min-h-11 cursor-pointer py-2 text-sm font-medium text-signal">{t("validation.show_numbers")}</summary>
          <ValidationTable data={data} />
        </details>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-[var(--radius-panel)] border border-border bg-surface p-5">
          <h3 className="font-bold">{t("validation.meaning_title")}</h3>
          <p className="mt-1 text-sm text-muted">{t(Math.abs(data.mean_error_pct) < 5 ? "validation.meaning_close" : lower ? "validation.meaning_lower" : "validation.meaning_higher")}</p>
        </div>
        <div className="rounded-[var(--radius-panel)] border border-border bg-surface p-5">
          <h3 className="font-bold">{t("validation.limits_title")}</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-muted">
            {VALIDATION_LIMITS.map((k) => <li key={k}>{t(`validation.${k}`)}</li>)}
          </ul>
        </div>
      </div>
      <p className="text-sm text-muted">
        {t("app.disclaimer")} {t("validation.source", { dataset: data.meta.dataset, doi: data.meta.dataset_doi, licence: data.meta.dataset_licence })}
      </p>
    </div>
  );
}

function Section({ id, title, lead, children }: { id: string; title: string; lead?: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="scroll-mt-20">
      <h2 id={`${id}-h`} className="text-2xl font-bold tracking-tight">{title}</h2>
      {lead && <p className="mt-1 max-w-prose text-muted">{lead}</p>}
      <div className="mt-5">{children}</div>
    </section>
  );
}
