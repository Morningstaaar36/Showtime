import { ChevronDown, ChevronLeft, Clock, Coins, History, Redo2, RotateCcw, Undo2 } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import { useRedo, useRestoreVersion, useUndo, useVersions } from "@/api/queries";
import type { CountdownOut, ProjectDetail } from "@/api/types";
import { Logo } from "@/components/Logo";
import { ProviderBadge } from "@/components/ProviderBadge";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tip } from "@/components/ui/tooltip";
import { Kbd, ScrollArea } from "@/components/ui/misc";
import { t } from "@/i18n";
import { fmtClock, fmtDuration, fmtHM, fmtMoney, fmtRelative, fmtTokens } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Mode } from "@/state/ui";

const MODES: { id: Mode; key: string; n: number }[] = [
  { id: "plan", key: "nav.plan", n: 1 },
  { id: "simulate", key: "nav.simulate", n: 2 },
  { id: "redteam", key: "nav.redteam", n: 3 },
  { id: "report", key: "nav.report", n: 4 },
];

export function TopBar({ project, mode, countdown, cost }: {
  project: ProjectDetail; mode: Mode; countdown: CountdownOut | undefined;
  cost: { tokens: number; usd: number } | null;
}) {
  const navigate = useNavigate();
  const undo = useUndo(project.id);
  const redo = useRedo(project.id);
  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-surface px-3">
      <Link to="/" aria-label="All projects" className="flex items-center gap-1 text-muted hover:text-ink">
        <ChevronLeft className="size-4" /><Logo compact />
      </Link>
      <div className="flex min-w-0 items-center gap-1.5 text-sm">
        <span className="truncate font-semibold">{project.name}</span>
        <span className="text-line">▸</span>
        <VersionMenu project={project} />
      </div>
      <div className="flex items-center gap-0.5">
        <Tip content={<span>{t("common.undo")} <Kbd>Ctrl</Kbd> <Kbd>Z</Kbd></span>}>
          <Button variant="ghost" size="icon-sm" aria-label={t("common.undo")} disabled={!project.can_undo || undo.isPending}
                  onClick={() => undo.mutate(undefined, { onSuccess: () => toast(t("workspace.undone")), onError: (e) => toast.error(e.message) })}>
            <Undo2 />
          </Button>
        </Tip>
        <Tip content={<span>{t("common.redo")} <Kbd>Ctrl</Kbd> <Kbd>Shift</Kbd> <Kbd>Z</Kbd></span>}>
          <Button variant="ghost" size="icon-sm" aria-label={t("common.redo")} disabled={!project.can_redo || redo.isPending}
                  onClick={() => redo.mutate(undefined, { onSuccess: () => toast(t("workspace.redone")), onError: (e) => toast.error(e.message) })}>
            <Redo2 />
          </Button>
        </Tip>
      </div>

      <nav aria-label="Workspace mode" className="mx-auto flex items-center rounded-[8px] bg-surface-2 p-0.5">
        {MODES.map((m) => (
          <button key={m.id} type="button" onClick={() => navigate(`/p/${project.id}/${m.id}`)}
                  aria-current={mode === m.id ? "page" : undefined}
                  className={cn("rounded-[6px] px-3.5 py-1 text-sm font-medium transition",
                    mode === m.id ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink")}>
            {t(m.key)}
          </button>
        ))}
      </nav>

      <CountdownChip data={countdown} />
      {cost && (
        <Tip content={`${cost.tokens.toLocaleString()} tokens used by AI agents in this project's red-team sessions`}>
          <span className="hidden h-7 items-center gap-1.5 rounded-[var(--radius-control)] border border-border px-2 text-xs tabular text-muted md:inline-flex">
            <Coins className="size-3.5" />{fmtTokens(cost.tokens)} · {fmtMoney(cost.usd)}
          </span>
        </Tip>
      )}
      <ProviderBadge />
      <ThemeToggle />
    </header>
  );
}

function VersionMenu({ project }: { project: ProjectDetail }) {
  const versions = useVersions(project.id);
  const restore = useRestoreVersion(project.id);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className="inline-flex items-center gap-1 rounded-[var(--radius-control)] px-1.5 py-0.5 text-muted hover:bg-surface-2 hover:text-ink">
          <span className="truncate">{project.venue_name}</span>
          <span className="tabular">v{project.current_version}</span>
          <ChevronDown className="size-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-0">
        <p className="flex items-center gap-2 border-b border-border px-4 py-2.5 text-sm font-semibold"><History className="size-4" />Version history</p>
        <ScrollArea className="max-h-80">
          <ul className="py-1">
            {(versions.data ?? []).map((v) => (
              <li key={v.version} className="group flex items-start gap-2 px-4 py-2 hover:bg-surface-2">
                <span className="mt-0.5 w-8 shrink-0 text-xs font-semibold text-muted tabular">v{v.version}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{v.message || "Edited"}</p>
                  <p className="text-xs text-muted">{v.author === "agent" ? "AI edit" : v.author === "system" ? "System" : "You"} · {fmtRelative(v.created_at)}</p>
                </div>
                {v.version !== project.current_version ? (
                  <Button size="sm" variant="ghost" className="opacity-0 group-hover:opacity-100 focus:opacity-100"
                          onClick={() => restore.mutate(v.version, { onSuccess: (r) => toast.success(t("workspace.saved", { n: r.version.version })) })}>
                    <RotateCcw />Restore
                  </Button>
                ) : <span className="text-xs text-egress">Current</span>}
              </li>
            ))}
          </ul>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}

function CountdownChip({ data }: { data: CountdownOut | undefined }) {
  const c = data?.countdown;
  let text = t("countdown.unknown");
  let tone = "border-border text-muted";
  if (c?.status === "ok") {
    text = c.t_latest_iso && c.hazard_source === "hazard_wind"
      ? t("countdown.start_by", { time: fmtHM(c.t_latest_iso) })
      : t("countdown.start_within", { d: fmtDuration(c.t_latest_s) });
    tone = "border-egress/40 bg-egress-soft text-ink";
  } else if (c?.status === "too_late") {
    text = "Too late to evacuate safely";
    tone = "border-danger/40 bg-danger-soft text-ink";
  } else if (c?.status === "no_hazard") {
    text = t("countdown.no_hazard");
  }
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className={cn("inline-flex h-7 max-w-64 items-center gap-1.5 rounded-[var(--radius-control)] border px-2 text-xs font-medium", tone)}>
          <Clock className="size-3.5 shrink-0" /><span className="truncate tabular">{text}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96">
        <p className="font-semibold">{t("countdown.title")}</p>
        {c ? (
          <dl className="mt-3 space-y-2 text-sm">
            <Row k={t("countdown.hazard")} v={c.t_hazard_s != null ? (c.t_hazard_iso ? fmtHM(c.t_hazard_iso) : `${fmtClock(c.t_hazard_s)} after the alarm`) : "none"} />
            <Row k={t("countdown.pre")} v={fmtDuration(c.pre_movement_s)} />
            <Row k={t("countdown.rset")} v={c.rset_s != null ? fmtDuration(c.rset_s) : "–"} />
            <Row k={t("countdown.sf")} v={`× ${c.safety_factor}`} />
            <div className="border-t border-border pt-2"><Row k="Latest start" v={c.t_latest_iso ? fmtHM(c.t_latest_iso) : c.t_latest_s != null ? fmtClock(c.t_latest_s) : "–"} strong /></div>
            <p className="pt-1 text-xs text-muted">{c.formula}</p>
            {c.hazard_explanation && <p className="text-xs text-muted">{c.hazard_explanation}</p>}
            {c.rset_source && <p className="text-xs text-muted">Evacuation time from: {c.rset_source}</p>}
          </dl>
        ) : <p className="mt-2 text-sm text-muted">{t("countdown.unknown")}</p>}
      </PopoverContent>
    </Popover>
  );
}

function Row({ k, v, strong }: { k: string; v: string; strong?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-muted">{k}</dt>
      <dd className={cn("tabular", strong && "font-semibold")}>{v}</dd>
    </div>
  );
}
