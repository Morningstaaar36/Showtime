/** Settings (route `/settings`): plain sections first (AI model, simulations, units and display);
 * safety limits, AI limits, services and plugins stay under "Advanced". */
import { Bot, ChevronDown, Monitor, Moon, Palette, Ruler, Sun, Users } from "lucide-react";
import type * as React from "react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useHealth, useSaveSettings, useSettings } from "@/api/queries";
import type { ProviderStatus } from "@/api/types";
import { AppShell } from "@/app/AppHeader";
import { ProviderBadge, providerWhere } from "@/components/ProviderBadge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { useUi } from "@/state/ui";

type Section = "ai" | "sims" | "density" | "limits";
interface Field { key: string; step: number; min: number; section: Section }

/** Labels, hints and units live in en.json as settings.f_<key>, settings.f_<key>_hint, settings.u_<key>. */
const FIELDS: Field[] = [
  { key: "max_rounds", step: 1, min: 1, section: "ai" },
  { key: "attacks_per_round", step: 1, min: 1, section: "ai" },
  { key: "fixes_per_attack", step: 1, min: 1, section: "ai" },
  { key: "max_people", step: 100, min: 100, section: "sims" },
  { key: "pre_movement_s", step: 5, min: 0, section: "sims" },
  { key: "safety_factor", step: 0.1, min: 1, section: "sims" },
  { key: "density_warn_ppm2", step: 0.1, min: 0.5, section: "density" },
  { key: "density_danger_ppm2", step: 0.1, min: 0.5, section: "density" },
  { key: "session_max_tokens", step: 10000, min: 10000, section: "limits" },
  { key: "tavily_max_calls", step: 1, min: 0, section: "limits" },
];

const fromServer = (src: Record<string, unknown> | undefined) =>
  Object.fromEntries(FIELDS.map((f) => [f.key, src?.[f.key] == null ? "" : String(src[f.key])]));

export function SettingsPage() {
  const settings = useSettings();
  const health = useHealth();
  const save = useSaveSettings();
  const [values, setValues] = useState<Record<string, string>>({});
  const units = useUi((s) => s.units);
  const setUnits = useUi((s) => s.setUnits);
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);

  useEffect(() => { if (settings.data) setValues(fromServer(settings.data.effective)); }, [settings.data]);
  const saved = useMemo(() => fromServer(settings.data?.effective), [settings.data]);
  const dirty = !!settings.data && FIELDS.some((f) => (values[f.key] ?? "") !== saved[f.key]);
  const defaults = settings.data?.defaults;

  const providers = health.data?.providers;
  const fields = (section: Section) => (
    <div className="grid gap-5 sm:grid-cols-2">
      {settings.isLoading && <><Skeleton className="h-24" /><Skeleton className="h-24" /></>}
      {settings.data && FIELDS.filter((f) => f.section === section).map((f) => (
        <NumberField key={f.key} field={f} value={values[f.key] ?? ""} fallback={defaults?.[f.key]}
                     onChange={(v) => setValues((cur) => ({ ...cur, [f.key]: v }))} />
      ))}
    </div>
  );
  const submit = () => {
    const out: Record<string, number> = {};
    for (const f of FIELDS) if (values[f.key] !== "") out[f.key] = Number(values[f.key]);
    save.mutate(out, { onSuccess: () => toast.success(t("settings.saved")), onError: (e) => toast.error(e.message, { description: (e as { hint?: string }).hint }) });
  };

  return (
    <AppShell className="bg-hero">
      <div className="mx-auto w-full max-w-4xl space-y-6 px-4 py-10">
        <div>
          <h1 className="text-3xl font-bold leading-tight tracking-tight sm:text-4xl">{t("settings.title")}</h1>
          <p className="mt-2 max-w-prose text-lg text-muted">{t("settings.lead")}</p>
        </div>
        {settings.isError && <ErrorState title={t("settings.load_error")} message={(settings.error as Error).message} onRetry={() => settings.refetch()} />}

        <Card id="ai" icon={<Bot />} tone="bg-signal-soft text-signal" title={t("settings.ai")} lead={t("settings.ai_lead")}>
          <div className="flex flex-col gap-3 rounded-[var(--radius-control)] bg-surface-2 p-4 sm:flex-row sm:items-start">
            <span className="shrink-0"><ProviderBadge /></span>
            <div className="min-w-0 space-y-1">
              <p className="font-semibold">{providerWhere(providers?.llm)}<Status ok={providers?.llm.ok} loading={health.isLoading} /></p>
              <p className="text-sm text-muted">{t("settings.badge_body")}</p>
            </div>
          </div>
          <p className="text-sm">{providers?.search.live ? t("settings.search_on") : t("settings.search_off")}</p>
          {fields("ai")}
        </Card>

        <Card id="sims" icon={<Users />} tone="bg-sky-soft text-sky" title={t("settings.sims")} lead={t("settings.sims_lead")}>
          <p className="text-sm">{providers?.sandbox.ok ? t("settings.sim_ready") : health.isLoading ? t("common.loading") : t("settings.sim_not_ready")}
            <Status ok={providers?.sandbox.ok} loading={health.isLoading} /></p>
          {fields("sims")}
        </Card>

        <Card id="display" icon={<Palette />} tone="bg-orange-soft text-orange" title={t("settings.display")} lead={t("settings.display_lead")}>
          <div className="grid gap-5 sm:grid-cols-2">
            <Choice label={t("settings.units")} icon={<Ruler />} value={units} onChange={(v) => setUnits(v as "metric" | "imperial")}
                    options={[["metric", t("settings.metric")], ["imperial", t("settings.imperial")]]} />
            <Choice label={t("settings.theme")} icon={<Monitor />} value={theme} onChange={(v) => setTheme(v as "light" | "dark" | "system")}
                    options={[["light", t("settings.theme_light"), <Sun key="s" />], ["dark", t("settings.theme_dark"), <Moon key="m" />], ["system", t("settings.theme_system"), <Monitor key="d" />]]} />
          </div>
        </Card>

        <details className="group rounded-[var(--radius-panel)] border border-border bg-surface shadow-sm">
          <summary className="flex min-h-14 cursor-pointer list-none items-center gap-3 px-5 py-3 sm:px-6">
            <span className="min-w-0 flex-1">
              <span className="block text-xl font-bold tracking-tight">{t("settings.advanced")}</span>
              <span className="block text-sm text-muted">{t("settings.advanced_lead")}</span>
            </span>
            <ChevronDown className="size-5 shrink-0 text-muted transition group-open:rotate-180" aria-hidden />
          </summary>
          <div className="space-y-8 border-t border-border p-5 sm:p-6">
            <Sub title={t("settings.density")}>{fields("density")}</Sub>
            <Sub title={t("settings.ai_limits")}>{fields("limits")}</Sub>
            <Sub title={t("settings.services")}>
              <dl className="grid gap-3 sm:grid-cols-2">
                {providers && ([["llm", t("settings.llm")], ["sandbox", t("settings.sandbox")], ["search", t("settings.search")], ["weather", t("settings.weather")]] as const)
                  .map(([k, label]) => <ServiceRow key={k} label={label} status={providers[k]} optional={k === "search"} />)}
                {health.isLoading && <Skeleton className="h-20 sm:col-span-2" />}
              </dl>
              {providers?.llm.models && (
                <div className="mt-4">
                  <p className="text-sm font-medium">{t("settings.models")}</p>
                  <ul className="mt-1.5 grid gap-1 text-sm text-muted sm:grid-cols-2">
                    {Object.entries(providers.llm.models).map(([role, model]) => (
                      <li key={role} className="break-all"><span className="font-medium text-ink">{role}</span> · {model}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="mt-4 text-sm text-muted">{t("settings.switch_hint")}</p>
            </Sub>
            <Sub title={t("settings.plugins")}>
              <ul className="divide-y divide-border text-sm">
                {(health.data?.plugins ?? []).map((p) => (
                  <li key={p.id} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 py-2">
                    <span aria-hidden className={cn("size-2 rounded-full", p.enabled && p.healthy ? "bg-egress" : p.enabled ? "bg-danger" : "bg-line")} />
                    <span className="font-medium">{p.name}</span>
                    <span className="text-muted">v{p.version}</span>
                    <span className="ml-auto text-xs text-muted">{p.provides.join(", ")}</span>
                  </li>
                ))}
              </ul>
            </Sub>
          </div>
        </details>

        <div className="sticky bottom-4 z-10 flex items-center justify-end gap-2 rounded-[var(--radius-panel)] border border-border bg-surface/95 p-2 shadow-[var(--shadow-float)] backdrop-blur sm:gap-3 sm:p-3">
          <p className="sr-only mr-auto text-sm text-muted sm:not-sr-only" aria-live="polite">{dirty ? t("settings.unsaved") : t("settings.all_saved")}</p>
          {defaults && (
            <Button variant="ghost" className="h-11 px-3" onClick={() => setValues(fromServer(defaults))}>{t("settings.restore")}</Button>
          )}
          <Button variant="primary" size="lg" disabled={!dirty || save.isPending} onClick={submit}>{t("settings.save")}</Button>
        </div>
      </div>
    </AppShell>
  );
}

function Card({ id, icon, tone, title, lead, children }: {
  id: string; icon: React.ReactNode; tone: string; title: string; lead: string; children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={`${id}-h`} className="rounded-[var(--radius-panel)] border border-border bg-surface p-5 shadow-sm sm:p-6">
      <div className="flex items-start gap-3">
        <span className={cn("grid size-11 shrink-0 place-items-center rounded-full [&_svg]:size-5", tone)} aria-hidden>{icon}</span>
        <div className="min-w-0">
          <h2 id={`${id}-h`} className="text-xl font-bold tracking-tight">{title}</h2>
          <p className="text-sm text-muted">{lead}</p>
        </div>
      </div>
      <div className="mt-5 space-y-5">{children}</div>
    </section>
  );
}

function Sub({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="text-base font-semibold">{title}</h3>
      {children}
    </section>
  );
}

function Status({ ok, loading }: { ok: boolean | undefined; loading: boolean }) {
  if (loading) return null;
  return (
    <span className={cn("ml-2 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 align-middle text-xs font-semibold text-ink",
      ok ? "bg-egress-soft" : "bg-caution-soft")}>
      <span aria-hidden className={cn("size-1.5 rounded-full", ok ? "bg-egress" : "bg-caution")} />{ok ? t("settings.ready") : t("settings.not_ready")}
    </span>
  );
}

function ServiceRow({ label, status, optional }: { label: string; status: ProviderStatus; optional?: boolean }) {
  const off = optional && status.ok && !status.live;
  return (
    <div className="rounded-[var(--radius-control)] border border-border p-3">
      <dt className="flex items-center justify-between gap-2 text-sm font-medium">
        {label}
        <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold text-ink",
          off ? "bg-surface-3" : status.ok ? "bg-egress-soft" : "bg-caution-soft")}>
          <span aria-hidden className={cn("size-1.5 rounded-full", off ? "bg-line" : status.ok ? "bg-egress" : "bg-caution")} />
          {off ? t("settings.off") : status.ok ? t("settings.ready") : t("settings.not_ready")}
        </span>
      </dt>
      <dd className="mt-1 break-words text-xs text-muted">{status.detail}</dd>
    </div>
  );
}

function NumberField({ field, value, fallback, onChange }: {
  field: Field; value: string; fallback: number | string | boolean | undefined; onChange: (v: string) => void;
}) {
  const id = `set-${field.key}`;
  return (
    <div className="grid content-start gap-1.5">
      <Label htmlFor={id}>{t(`settings.f_${field.key}`)}</Label>
      <div className="flex items-center gap-2">
        <Input id={id} type="number" inputMode="decimal" step={field.step} min={field.min} value={value}
               onChange={(e) => onChange(e.target.value)} aria-describedby={`${id}-hint`} className="h-11 max-w-36 text-base" />
        <span className="text-sm text-muted">{t(`settings.u_${field.key}`)}</span>
      </div>
      <p id={`${id}-hint`} className="text-xs text-muted">
        {t(`settings.f_${field.key}_hint`)}{fallback != null && ` ${t("settings.default_is", { v: String(fallback) })}`}
      </p>
    </div>
  );
}

/** Buttons in a row; the picked one is filled. */
function Choice({ label, icon, value, options, onChange }: {
  label: string; icon: React.ReactNode; value: string; options: [string, string, React.ReactNode?][]; onChange: (v: string) => void;
}) {
  return (
    <div role="group" aria-label={label}>
      <p className="flex items-center gap-1.5 text-sm font-medium [&_svg]:size-4 [&_svg]:text-muted">{icon}{label}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {options.map(([v, l, ic]) => (
          <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}
                  className={cn("inline-flex min-h-11 items-center gap-1.5 rounded-[var(--radius-control)] border-2 px-3 text-sm font-medium transition [&_svg]:size-4",
                    value === v ? "border-signal bg-signal-soft text-ink" : "border-border text-muted hover:border-border-strong hover:text-ink")}>
            {ic}{l}
          </button>
        ))}
      </div>
    </div>
  );
}
