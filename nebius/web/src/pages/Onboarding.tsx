import { CheckCircle2, CircleDashed, CircleMinus } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { useHealth, useProjects } from "@/api/queries";
import { AppHeader } from "@/app/AppHeader";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/misc";
import { t } from "@/i18n";
import { useUi } from "@/state/ui";

function Row({ label, state, hint }: { label: string; state: "ok" | "off" | "missing" | "loading"; hint?: string }) {
  const icon = state === "ok" ? <CheckCircle2 className="size-5 text-egress" />
    : state === "off" ? <CircleMinus className="size-5 text-line" />
    : state === "loading" ? <Spinner className="size-5" /> : <CircleDashed className="size-5 text-caution" />;
  return (
    <li className="flex items-start gap-3 py-3">
      {icon}
      <div className="min-w-0 flex-1">
        <p className="font-medium">{label}</p>
        {state !== "ok" && hint && <p className="text-sm text-muted">{hint}</p>}
      </div>
      <span className="text-sm text-muted">{state === "ok" ? t("onboarding.ok") : state === "off" ? t("onboarding.off") : state === "loading" ? "" : t("onboarding.missing")}</span>
    </li>
  );
}

export function OnboardingPage() {
  const health = useHealth();
  const projects = useProjects();
  const navigate = useNavigate();
  const h = health.data?.providers;
  const samples = (projects.data ?? []).filter((p) => p.sample);
  const st = (ok?: boolean) => (health.isLoading ? "loading" : ok ? "ok" : "missing") as "ok" | "missing" | "loading";
  return (
    <div className="min-h-full">
      <AppHeader />
      <main id="main" className="mx-auto max-w-3xl px-4 py-12">
        <h1 className="text-3xl font-semibold tracking-tight">{t("onboarding.title")}</h1>
        <p className="mt-3 max-w-prose text-muted">{t("onboarding.lead")}</p>
        <section className="mt-8 rounded-[10px] border border-border bg-surface px-5">
          <h2 className="pt-4 text-sm font-semibold">{t("onboarding.checklist")}</h2>
          <ul className="divide-y divide-border">
            <Row label={t("onboarding.check_model")} state={st(h?.llm.ok)} hint={t("onboarding.hint_model")} />
            <Row label={t("onboarding.check_docker")} state={st(h?.sandbox.ok)} hint={t("onboarding.hint_docker")} />
            <Row label={t("onboarding.check_search")} state={health.isLoading ? "loading" : h?.search.live ? "ok" : "off"} hint={t("onboarding.hint_search")} />
            <Row label={t("onboarding.check_samples")} state={projects.isLoading ? "loading" : samples.length ? "ok" : "missing"} hint="Run: make demo-precompute" />
          </ul>
        </section>
        <div className="mt-6 flex flex-wrap gap-2">
          <Button variant="primary" size="lg" disabled={!samples.length}
                  onClick={() => { useUi.getState().resetForProject(); navigate(`/p/${samples[0].id}`); }}>
            {t("onboarding.open_sample")}
          </Button>
          <Button asChild size="lg"><Link to="/">{t("onboarding.go_projects")}</Link></Button>
        </div>
      </main>
    </div>
  );
}
