import { ChevronDown, ChevronLeft, Clock, FileCode2, History, Redo2, RotateCcw, Undo2 } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import { useRedo, useRestoreVersion, useUndo, useVersions } from "@/api/queries";
import type { CountdownOut, ProjectDetail } from "@/api/types";
import { Logo } from "@/components/Logo";
import { ProviderBadge } from "@/components/ProviderBadge";
import { SandboxBadge } from "@/components/SandboxBadge";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tip } from "@/components/ui/tooltip";
import { Kbd, ScrollArea } from "@/components/ui/misc";
import { t } from "@/i18n";
import { fmtClock, fmtDuration, fmtHM, fmtRelative } from "@/lib/format";
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
    <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-surface px-3">
      <Link to="/" aria-label={t("common.home_label")} className="shrink-0 rounded-[var(--radius-control)]"><Logo compact /></Link>
      <Link to={`/p/${project.id}`}
            className="inline-flex h-9 shrink-0 items-center gap-1 rounded-full bg-signal-soft pl-2 pr-3.5 text-sm font-semibold text-signal transition hover:brightness-95">
        <ChevronLeft className="size-4" aria-hidden />{t("journey.simple_view")}
      </Link>
      <div className="flex min-w-0 items-center gap-1.5 pl-1 text-sm">
        <span className="truncate font-semibold" title={project.name}>{project.name}</span>
        <span className="text-line" aria-hidden>▸</span>
        <VersionMenu project={project} />
      </div>
      <div className="flex shrink-0 items-center gap-0.5">
        <Tip content={<span>{t("common.undo")} <Kbd>{t("ui.topbar.ctrl")}</Kbd> <Kbd>Z</Kbd></span>}>
          <Button variant="ghost" size="icon" aria-label={t("common.undo")} disabled={!project.can_undo || undo.isPending}
                  onClick={() => undo.mutate(undefined, { onSuccess: () => toast(t("workspace.undone")), onError: (e) => toast.error(e.message) })}>
            <Undo2 />
          </Button>
        </Tip>
        <Tip content={<span>{t("common.redo")} <Kbd>{t("ui.topbar.ctrl")}</Kbd> <Kbd>{t("ui.topbar.shift")}</Kbd> <Kbd>Z</Kbd></span>}>
          <Button variant="ghost" size="icon" aria-label={t("common.redo")} disabled={!project.can_redo || redo.isPending}
                  onClick={() => redo.mutate(undefined, { onSuccess: () => toast(t("workspace.redone")), onError: (e) => toast.error(e.message) })}>
            <Redo2 />
          </Button>
        </Tip>
      </div>

      <nav aria-label={t("workspace.modes")} className="mx-auto flex shrink-0 items-center gap-0.5 rounded-full bg-surface-2 p-1">
        {MODES.map((m) => (
          <button key={m.id} type="button" onClick={() => navigate(`/p/${project.id}/expert/${m.id}`)}
                  aria-current={mode === m.id ? "page" : undefined} aria-keyshortcuts={String(m.n)}
                  className={cn("whitespace-nowrap rounded-full px-4 py-1.5 text-sm font-medium transition",
                    mode === m.id ? "bg-signal text-signal-ink shadow-sm" : "text-muted hover:bg-surface hover:text-ink")}>
            {t(m.key)}
          </button>
        ))}
      </nav>

      <Link to={`/p/${project.id}/scripts`}
            className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full px-3 text-sm font-medium text-muted hover:bg-surface-2 hover:text-ink">
        <FileCode2 className="size-4" aria-hidden />{t("userscripts.open")}
      </Link>
      <CountdownChip data={countdown} />
      {/* the project's AI cost lives in the provider badge popover */}
      <ProviderBadge cost={cost} />
      <SandboxBadge />
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
        <p className="flex items-center gap-2 border-b border-border px-4 py-2.5 text-sm font-semibold"><History className="size-4" />{t("ui.topbar.version_history")}</p>
        <ScrollArea className="max-h-80">
          <ul className="py-1">
            {(versions.data ?? []).map((v) => (
              <li key={v.version} className="group flex items-start gap-2 px-4 py-2 hover:bg-surface-2">
                <span className="mt-0.5 w-8 shrink-0 text-xs font-semibold text-muted tabular">v{v.version}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{v.message || t("ui.topbar.edited")}</p>
                  <p className="text-xs text-muted">{v.author === "agent" ? t("ui.topbar.ai_edit") : v.author === "system" ? t("ui.topbar.system") : t("ui.topbar.you")} · {fmtRelative(v.created_at)}</p>
                </div>
                {v.version !== project.current_version ? (
                  <Button size="sm" variant="ghost" className="opacity-0 group-hover:opacity-100 focus:opacity-100"
                          onClick={() => restore.mutate(v.version, { onSuccess: (r) => toast.success(t("workspace.saved", { n: r.version.version })) })}>
                    <RotateCcw />{t("ui.topbar.restore")}</Button>
                ) : <span className="text-xs text-egress">{t("ui.topbar.current")}</span>}
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
        <button type="button" className={cn("inline-flex h-8 max-w-48 shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs font-medium xl:max-w-64", tone)}>
          <Clock className="size-3.5 shrink-0" /><span className="truncate tabular">{text}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96">
        <p className="font-semibold">{t("countdown.title")}</p>
        {c ? (
          <dl className="mt-3 space-y-2 text-sm">
            <Row k={t("countdown.hazard")} v={c.t_hazard_s != null ? (c.t_hazard_iso ? fmtHM(c.t_hazard_iso) : t("ui.topbar.after_alarm", { at: fmtClock(c.t_hazard_s) })) : "none"} />
            <Row k={t("countdown.pre")} v={fmtDuration(c.pre_movement_s)} />
            <Row k={t("countdown.rset")} v={c.rset_s != null ? fmtDuration(c.rset_s) : "–"} />
            <Row k={t("countdown.sf")} v={`× ${c.safety_factor}`} />
            <div className="border-t border-border pt-2"><Row k="Latest start" v={c.t_latest_iso ? fmtHM(c.t_latest_iso) : c.t_latest_s != null ? fmtClock(c.t_latest_s) : "–"} strong /></div>
            <p className="pt-1 text-xs text-muted">{c.formula}</p>
            {c.hazard_explanation && <p className="text-xs text-muted">{c.hazard_explanation}</p>}
            {c.rset_source && <p className="text-xs text-muted">{t("ui.topbar.rset_source", { source: c.rset_source })}</p>}
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
