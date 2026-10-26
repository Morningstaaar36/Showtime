/** The AI team (route `/team`): every NVIDIA Nemotron agent in the order it works, what it
 * decides, the model it runs on now and the tools it may use; and the sandbox every simulation
 * runs in. Agents decide; tools (solver, simulator, number check) produce every number. */
import { Bot, Box, Building2, Calculator, CheckCheck, Code2, Gauge, Globe, Map as MapIcon, Pencil, ShieldCheck, Swords, Wrench, Zap } from "lucide-react";
import type * as React from "react";
import { useAgents, type AgentInfo } from "@/api/queries";
import { AppShell } from "@/app/AppHeader";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

const STAGES = ["build", "attack", "defend", "judge", "explain"] as const;

const STAGE_TONE: Record<(typeof STAGES)[number], string> = {
  build: "bg-sky-soft text-sky",
  attack: "bg-danger-soft text-danger-strong",
  defend: "bg-egress-soft text-egress-strong",
  judge: "bg-signal-soft text-signal",
  explain: "bg-surface-3 text-ink",
};

const TOOL_ICON: Record<string, React.ReactNode> = {
  simulator: <Box />,
  instant_estimate: <Zap />,
  solver: <Building2 />,
  map: <MapIcon />,
  incidents: <Swords />,
  edit_ops: <Pencil />,
  scenario_events: <Gauge />,
  number_check: <CheckCheck />,
  search: <Globe />,
  code_sandbox: <Code2 />,
};

/** "nvidia/nemotron-3.5-lightning:free" → "Nemotron 3.5 Lightning" */
export function modelName(id: string): string {
  const base = id.split("/").pop()?.split(":")[0] ?? id;
  return base
    .replace(/-(\d+b)(-a\d+b)?$/i, "")
    .split("-")
    .map((w) => (/^\d/.test(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

function AgentCard({ a, tools }: { a: AgentInfo; tools: Record<string, string> }) {
  return (
    <li className="space-y-2 rounded-[var(--radius-panel)] border border-border bg-surface p-3 shadow-sm">
      <div className="flex items-center gap-2">
        <span className="grid size-8 place-items-center rounded-full bg-surface-2 [&_svg]:size-4" aria-hidden><Bot /></span>
        <span className="font-semibold">{a.label}</span>
      </div>
      <p className="text-sm leading-snug text-muted">{a.decides}</p>
      <p className="inline-flex rounded-full bg-signal-soft px-2 py-0.5 text-2xs font-medium text-signal" title={a.model}>{modelName(a.model)}</p>
      {a.tools.length > 0 && (
        <ul className="flex flex-wrap gap-1" aria-label={t("team.tools")}>
          {a.tools.map((x) => (
            <li key={x} title={tools[x] ?? x} className="inline-flex items-center gap-1 rounded-[6px] border border-border px-1.5 py-0.5 text-2xs text-muted [&_svg]:size-3">
              {TOOL_ICON[x]}{t(`team.tool_${x}`)}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export function TeamPage() {
  const q = useAgents();
  const agents = q.data?.agents ?? [];
  return (
    <AppShell className="bg-hero">
      <div className="mx-auto w-full max-w-6xl space-y-8 px-4 py-10">
        <div>
          <h1 className="text-3xl font-bold leading-tight tracking-tight sm:text-4xl">{t("team.title")}</h1>
          <p className="mt-2 max-w-prose text-lg text-muted">{t("team.lead")}</p>
        </div>
        {q.isError && <p className="text-sm text-danger">{t("team.error")}</p>}
        <ol className="grid grid-cols-1 gap-4 md:grid-cols-5" aria-label={t("team.title")}>
          {STAGES.map((s, i) => (
            <li key={s} className="space-y-3">
              <p className={cn("flex items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold", STAGE_TONE[s])}>
                <span className="tabular">{i + 1}</span>{t(`team.stage_${s}`)}
              </p>
              <ul className="space-y-3">
                {agents.filter((a) => a.stage === s).map((a) => <AgentCard key={a.name} a={a} tools={q.data?.tools ?? {}} />)}
              </ul>
            </li>
          ))}
        </ol>
        {q.data && (
          <section aria-labelledby="sandbox-h" className="flex flex-wrap items-start gap-4 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
            <span className={cn("grid size-10 place-items-center rounded-[10px] [&_svg]:size-5", q.data.sandbox.ok ? "bg-egress-soft text-egress-strong" : "bg-caution-soft text-caution-strong")} aria-hidden><ShieldCheck /></span>
            <div className="min-w-0 flex-1 space-y-1">
              <h2 id="sandbox-h" className="font-semibold">{t("team.sandbox_title")}</h2>
              <p className="text-sm text-muted">{t("team.sandbox_text", { where: q.data.sandbox.title ?? q.data.sandbox.provider })}</p>
              <p className="text-xs text-muted" data-testid="team-isolation">{q.data.sandbox.isolation.summary} · {q.data.sandbox.detail}</p>
            </div>
            <div className="flex items-center gap-2 text-sm text-muted"><Calculator className="size-4" aria-hidden />{t("team.numbers")}</div>
            <div className="flex items-center gap-2 text-sm text-muted"><Wrench className="size-4" aria-hidden />{t("team.kept")}</div>
          </section>
        )}
      </div>
    </AppShell>
  );
}
