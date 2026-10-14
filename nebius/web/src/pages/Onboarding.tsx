/** First run (route `/welcome`): is everything ready on this computer, then open a sample or plan
 * your own event. */
import { CheckCircle2, CircleDashed, CircleMinus, Sparkles } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { useHealth, useProjects } from "@/api/queries";
import { AppShell } from "@/app/AppHeader";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/misc";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { useUi } from "@/state/ui";

type State = "ok" | "off" | "missing" | "loading";

const TONE: Record<State, string> = {
  ok: "bg-egress-soft text-egress", off: "bg-surface-3 text-muted", missing: "bg-caution-soft text-caution", loading: "bg-surface-3 text-muted",
};

function Row({ label, state, hint }: { label: string; state: State; hint?: string }) {
  const icon = state === "ok" ? <CheckCircle2 /> : state === "off" ? <CircleMinus /> : state === "loading" ? <Spinner /> : <CircleDashed />;
  return (
    <li className="flex items-start gap-3 py-3.5">
      <span className={cn("grid size-9 shrink-0 place-items-center rounded-full [&_svg]:size-5", TONE[state])} aria-hidden>{icon}</span>
      <div className="min-w-0 flex-1 pt-1.5">
        <p className="font-medium">{label}</p>
        {state !== "ok" && state !== "loading" && hint && <p className="mt-0.5 text-sm text-muted">{hint}</p>}
      </div>
      {state !== "loading" && (
        <span className={cn("mt-1.5 shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold", TONE[state], "text-ink")}>
          {state === "ok" ? t("onboarding.ok") : state === "off" ? t("onboarding.off") : t("onboarding.missing")}
        </span>
      )}
    </li>
  );
}

export function OnboardingPage() {
  const health = useHealth();
  const projects = useProjects();
  const navigate = useNavigate();
  const h = health.data?.providers;
  const samples = (projects.data ?? []).filter((p) => p.sample);
  const st = (ok?: boolean): State => (health.isLoading ? "loading" : ok ? "ok" : "missing");
  return (
    <AppShell className="bg-hero">
      <div className="mx-auto w-full max-w-3xl px-4 py-12">
        <span className="grid size-14 place-items-center rounded-full bg-signal-soft text-signal [&_svg]:size-7" aria-hidden><Sparkles /></span>
        <h1 className="mt-4 text-3xl font-bold leading-tight tracking-tight sm:text-4xl">{t("onboarding.title")}</h1>
        <p className="mt-2 max-w-prose text-lg text-muted">{t("onboarding.lead")}</p>
        <section aria-labelledby="check-h" className="mt-8 rounded-[var(--radius-panel)] border border-border bg-surface px-5 pt-5 shadow-sm">
          <h2 id="check-h" className="text-lg font-bold">{t("onboarding.checklist")}</h2>
          <p className="text-sm text-muted">{t("onboarding.checklist_lead")}</p>
          <ul className="mt-2 divide-y divide-border">
            <Row label={t("onboarding.check_model")} state={st(h?.llm.ok)} hint={t("onboarding.hint_model")} />
            <Row label={t("onboarding.check_docker")} state={st(h?.sandbox.ok)} hint={t("onboarding.hint_docker")} />
            <Row label={t("onboarding.check_search")} state={health.isLoading ? "loading" : h?.search.live ? "ok" : "off"} hint={t("onboarding.hint_search")} />
            <Row label={t("onboarding.check_samples")} state={projects.isLoading ? "loading" : samples.length ? "ok" : "missing"} hint={t("onboarding.hint_samples")} />
          </ul>
        </section>
        <div className="mt-6 flex flex-wrap gap-2">
          <Button variant="primary" size="lg" disabled={!samples.length}
                  onClick={() => { useUi.getState().resetForProject(); navigate(`/p/${samples[0].id}`); }}>
            {t("onboarding.open_sample")}
          </Button>
          <Button asChild size="lg"><Link to="/">{t("onboarding.go_projects")}</Link></Button>
        </div>
      </div>
    </AppShell>
  );
}
