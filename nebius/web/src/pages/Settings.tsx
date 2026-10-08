import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useHealth, useSaveSettings, useSettings } from "@/api/queries";
import { AppHeader } from "@/app/AppHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { useUi } from "@/state/ui";

const FIELDS: { key: string; label: string; unit: string; step: number; section: "thresholds" | "budgets" }[] = [
  { key: "pre_movement_s", label: "Pre-movement time", unit: "s", step: 5, section: "thresholds" },
  { key: "safety_factor", label: "Safety factor on evacuation time", unit: "×", step: 0.1, section: "thresholds" },
  { key: "density_warn_ppm2", label: "Warning density", unit: "people per m²", step: 0.1, section: "thresholds" },
  { key: "density_danger_ppm2", label: "Danger density", unit: "people per m²", step: 0.1, section: "thresholds" },
  { key: "max_people", label: "People limit per simulation", unit: "people", step: 100, section: "budgets" },
  { key: "max_rounds", label: "Red-team rounds", unit: "rounds", step: 1, section: "budgets" },
  { key: "attacks_per_round", label: "Attacks per round", unit: "attacks", step: 1, section: "budgets" },
  { key: "fixes_per_attack", label: "Fixes per attack", unit: "fixes", step: 1, section: "budgets" },
  { key: "session_max_tokens", label: "Token budget per session", unit: "tokens", step: 10000, section: "budgets" },
  { key: "tavily_max_calls", label: "Web searches per session", unit: "calls", step: 1, section: "budgets" },
];

export function SettingsPage() {
  const settings = useSettings();
  const health = useHealth();
  const save = useSaveSettings();
  const [values, setValues] = useState<Record<string, string>>({});
  const units = useUi((s) => s.units);
  const setUnits = useUi((s) => s.setUnits);
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);

  useEffect(() => {
    if (settings.data) setValues(Object.fromEntries(FIELDS.map((f) => [f.key, String(settings.data.effective[f.key] ?? "")])));
  }, [settings.data]);

  const providers = health.data?.providers;
  return (
    <div className="min-h-full">
      <AppHeader />
      <main id="main" className="mx-auto max-w-4xl space-y-8 px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight">{t("settings.title")}</h1>
        <section className="rounded-[10px] border border-border bg-surface p-5">
          <h2 className="font-semibold">{t("settings.providers")}</h2>
          <dl className="mt-4 grid gap-3 sm:grid-cols-2">
            {providers && ([["llm", t("settings.llm")], ["sandbox", t("settings.sandbox")], ["search", t("settings.search")], ["weather", t("settings.weather")]] as const).map(([k, label]) => {
              const p = providers[k];
              return (
                <div key={k} className="rounded-[8px] border border-border p-3">
                  <dt className="flex items-center justify-between text-sm font-medium">{label}
                    <Badge tone={p.ok ? (k === "search" && !p.live ? "neutral" : "egress") : "caution"}>{p.ok ? (k === "search" && !p.live ? "Off" : "Ready") : "Not ready"}</Badge>
                  </dt>
                  <dd className="mt-1 break-words text-xs text-muted">{p.detail}</dd>
                </div>
              );
            })}
            {health.isLoading && <Skeleton className="h-20 sm:col-span-2" />}
          </dl>
          <p className="mt-4 text-sm text-muted">{t("settings.switch_hint")}</p>
        </section>

        {settings.isError && <ErrorState message={(settings.error as Error).message} onRetry={() => settings.refetch()} />}
        {(["thresholds", "budgets"] as const).map((section) => (
          <section key={section} className="rounded-[10px] border border-border bg-surface p-5">
            <h2 className="font-semibold">{t(`settings.${section}`)}</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {FIELDS.filter((f) => f.section === section).map((f) => (
                <div key={f.key} className="grid gap-1.5">
                  <Label htmlFor={f.key}>{f.label}</Label>
                  <div className="flex items-center gap-2">
                    <Input id={f.key} type="number" step={f.step} value={values[f.key] ?? ""}
                           onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))} className="max-w-40" />
                    <span className="text-sm text-muted">{f.unit}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}

        <section className="rounded-[10px] border border-border bg-surface p-5">
          <h2 className="font-semibold">{t("settings.display")}</h2>
          <div className="mt-4 flex flex-wrap gap-8">
            <Segmented label={t("settings.units")} value={units} onChange={(v) => setUnits(v as "metric" | "imperial")}
                       options={[["metric", t("settings.metric")], ["imperial", t("settings.imperial")]]} />
            <Segmented label={t("settings.theme")} value={theme} onChange={(v) => setTheme(v as "light" | "dark" | "system")}
                       options={[["system", "System"], ["light", "Light"], ["dark", "Dark"]]} />
          </div>
        </section>

        <section className="rounded-[10px] border border-border bg-surface p-5">
          <h2 className="font-semibold">{t("settings.plugins")}</h2>
          <ul className="mt-3 divide-y divide-border text-sm">
            {(health.data?.plugins ?? []).map((p) => (
              <li key={p.id} className="flex items-center gap-3 py-2">
                <span className={cn("size-2 rounded-full", p.enabled && p.healthy ? "bg-egress" : p.enabled ? "bg-danger" : "bg-line")} />
                <span className="font-medium">{p.name}</span>
                <span className="text-muted">v{p.version}</span>
                <span className="ml-auto text-xs text-muted">{p.provides.join(", ")}</span>
              </li>
            ))}
          </ul>
        </section>

        <div className="sticky bottom-4 flex justify-end">
          <Button variant="primary" size="lg" disabled={save.isPending} onClick={() => {
            const out: Record<string, number> = {};
            for (const f of FIELDS) if (values[f.key] !== "") out[f.key] = Number(values[f.key]);
            save.mutate(out, { onSuccess: () => toast.success(t("settings.saved")), onError: (e) => toast.error(e.message) });
          }}>{t("settings.save")}</Button>
        </div>
      </main>
    </div>
  );
}

function Segmented({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void }) {
  return (
    <div>
      <p className="text-sm font-medium">{label}</p>
      <div role="radiogroup" aria-label={label} className="mt-2 inline-flex rounded-[var(--radius-control)] border border-border bg-surface-2 p-0.5">
        {options.map(([v, l]) => (
          <button key={v} role="radio" aria-checked={value === v} type="button" onClick={() => onChange(v)}
                  className={cn("rounded-[5px] px-3 py-1 text-sm", value === v ? "bg-surface font-medium shadow-sm" : "text-muted hover:text-ink")}>
            {l}
          </button>
        ))}
      </div>
    </div>
  );
}
