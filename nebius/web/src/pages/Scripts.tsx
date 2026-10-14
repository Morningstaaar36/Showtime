/** Scripts (route `/p/:projectId/scripts`, linked from Expert view): bring your own model.
 * Write or upload an analysis script (reads a simulated run with showtime_data) or a scenario
 * script (on_step(view, act) during a quick simulation), save it with the project and run it in a
 * sealed sandbox. The output, the messages and the code stay with the script. */
import { ChevronLeft, FileCode2, Play, Plus, Save, Trash2, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import {
  type UserScript,
  type UserScriptIn,
  type UserScriptKind,
  type UserScriptRun,
  useDeleteScript,
  useProject,
  useRun,
  useRunScript,
  useSaveScript,
  useScripts,
} from "@/api/queries";
import { ApiError } from "@/api/client";
import { AppShell } from "@/app/AppHeader";
import { Confirm } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton, Spinner } from "@/components/ui/misc";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { fmtDuration, fmtNum, fmtRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { AnalysisCard } from "@/journey/AnalysisCard";
import { guessKind, readScriptFile, starterScript } from "@/journey/analysis";
import { useUi } from "@/state/ui";

type Draft = UserScriptIn & { id: string | null };

const FIELD = "w-full rounded-[var(--radius-control)] border border-border bg-surface px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-signal";

function draftOf(s: UserScript): Draft {
  return { id: s.id, name: s.name, kind: s.kind, code: s.code, every_s: s.every_s };
}

function same(a: Draft, s: UserScript | undefined): boolean {
  return !!s && a.name === s.name && a.kind === s.kind && a.code === s.code && a.every_s === s.every_s;
}

export function ScriptsPage() {
  const { projectId = "" } = useParams();
  const project = useProject(projectId);
  const list = useScripts(projectId);
  const save = useSaveScript(projectId);
  const remove = useDeleteScript(projectId);
  const run = useRunScript(projectId);
  const fileInput = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [confirm, setConfirm] = useState(false);

  const scripts = useMemo(() => list.data?.scripts ?? [], [list.data]);
  const saved = scripts.find((s) => s.id === draft?.id);
  const firstExit = project.data?.version.venue.floors.flatMap((f) => f.exits)[0]?.id ?? null;
  const dirty = draft !== null && !same(draft, saved);

  // open the newest script once the list arrives
  useEffect(() => {
    if (draft === null && scripts.length) setDraft(draftOf(scripts[0]));
  }, [scripts, draft]);

  const startNew = (kind: UserScriptKind = "analysis", code?: string, name?: string) =>
    setDraft({ id: null, name: name ?? "", kind, code: code ?? starterScript(kind, firstExit), every_s: 1 });

  const onUpload = async (file: File | undefined) => {
    if (!file) return;
    const code = await readScriptFile(file);
    if (code === null) { toast.error(t("userscripts.upload_too_big")); return; }
    startNew(guessKind(code), code, file.name.replace(/\.py$/i, "").slice(0, 80));
  };

  const doSave = async (): Promise<UserScript | null> => {
    if (!draft) return null;
    const body = { ...draft, name: draft.name.trim() || t("userscripts.new") };
    try {
      const s = await save.mutateAsync(body);
      setDraft(draftOf(s));
      return s;
    } catch (e) {
      toast.error((e as Error).message);
      return null;
    }
  };

  const doRun = async () => {
    const s = dirty || !draft?.id ? await doSave() : saved;
    if (!s) return;
    if (s.problems.length) { toast.error(t("userscripts.problems")); return; }
    run.mutate({ id: s.id }, {
      onError: (e) => toast.error(e.message, { description: e instanceof ApiError ? e.hint ?? undefined : undefined }),
    });
  };

  if (project.isError) {
    return (
      <AppShell className="bg-hero">
        <div className="mx-auto w-full max-w-2xl px-4 py-12">
          <ErrorState message={t("userscripts.missing_project")} />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell className="bg-hero">
      <div className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8">
        <div>
          <Link to={`/p/${projectId}/expert`} className="inline-flex min-h-11 items-center gap-1 text-sm font-medium text-signal hover:underline">
            <ChevronLeft className="size-4" aria-hidden />{t("userscripts.back")}
          </Link>
          <h1 className="text-3xl font-bold leading-tight tracking-tight">{t("userscripts.title")}</h1>
          <p className="mt-1 max-w-prose text-muted">{t("userscripts.lead")}</p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
          <aside aria-label={t("userscripts.list")} className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" onClick={() => startNew()}><Plus />{t("userscripts.new")}</Button>
              <Button onClick={() => fileInput.current?.click()}><Upload />{t("userscripts.upload")}</Button>
              <input ref={fileInput} type="file" accept=".py,text/x-python,text/plain" className="sr-only" tabIndex={-1}
                     aria-hidden onChange={(e) => { void onUpload(e.target.files?.[0]); e.target.value = ""; }} />
            </div>
            {list.isPending && <Skeleton className="h-24" />}
            {list.isError && <ErrorState message={(list.error as Error).message} onRetry={() => list.refetch()} />}
            {list.data && !scripts.length && draft === null && (
              <EmptyState icon={<FileCode2 />} title={t("userscripts.empty_title")} body={t("userscripts.empty_body")} />
            )}
            <ul className="space-y-1.5">
              {scripts.map((s) => (
                <li key={s.id}>
                  <button type="button" onClick={() => setDraft(draftOf(s))} aria-current={draft?.id === s.id ? "true" : undefined}
                          className={cn("flex min-h-11 w-full flex-col items-start rounded-[var(--radius-control)] border px-3 py-2 text-left text-sm transition",
                            draft?.id === s.id ? "border-signal bg-signal-soft" : "border-border bg-surface hover:border-border-strong")}>
                    <span className="w-full truncate font-medium">{s.name}</span>
                    <span className="text-xs text-muted">
                      {t(`userscripts.kind_${s.kind}`)}{s.last_run ? ` · ${t(`userscripts.status_${s.last_run.status}`)}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          {draft && (
            <section aria-label={t("userscripts.code")} className="min-w-0 space-y-4 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
              <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                <label className="space-y-1 text-sm">
                  <span className="font-medium">{t("userscripts.name")}</span>
                  <input className={FIELD} value={draft.name} maxLength={80} placeholder={t("userscripts.name_ph")}
                         onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
                </label>
                <fieldset className="space-y-1 text-sm">
                  <legend className="font-medium">{t("userscripts.kind")}</legend>
                  <div className="flex gap-1 rounded-full bg-surface-2 p-1">
                    {(["analysis", "scenario"] as const).map((k) => (
                      <button key={k} type="button" aria-pressed={draft.kind === k}
                              onClick={() => setDraft({ ...draft, kind: k })}
                              className={cn("min-h-9 rounded-full px-4 text-sm font-medium transition",
                                draft.kind === k ? "bg-signal text-signal-ink shadow-sm" : "text-muted hover:bg-surface hover:text-ink")}>
                        {t(`userscripts.kind_${k}`)}
                      </button>
                    ))}
                  </div>
                </fieldset>
              </div>
              <p className="text-sm text-muted">{t(`userscripts.kind_${draft.kind}_help`)}</p>
              {draft.kind === "scenario" && list.data && !list.data.scenario_supported && (
                <p className="rounded-[8px] bg-caution-soft px-3 py-2 text-sm">{t("userscripts.scenario_unsupported")}</p>
              )}
              {draft.kind === "scenario" && (
                <label className="flex items-center gap-2 text-sm">
                  <span>{t("userscripts.every")}</span>
                  <input type="number" min={0.5} max={60} step={0.5} className={cn(FIELD, "w-24")} value={draft.every_s}
                         onChange={(e) => setDraft({ ...draft, every_s: Math.min(60, Math.max(0.5, Number(e.target.value) || 1)) })} />
                </label>
              )}
              <label className="block space-y-1 text-sm">
                <span className="font-medium">{t("userscripts.code")}</span>
                <textarea className={cn(FIELD, "min-h-[22rem] font-mono text-xs leading-relaxed")} spellCheck={false}
                          value={draft.code} maxLength={16384} onChange={(e) => setDraft({ ...draft, code: e.target.value })} />
              </label>
              {saved && saved.problems.length > 0 && !dirty && (
                <div role="alert" className="rounded-[8px] border border-caution/40 bg-caution-soft px-3 py-2 text-sm">
                  <p className="font-medium">{t("userscripts.problems")}</p>
                  <ul className="mt-1 list-disc pl-5">{saved.problems.map((p) => <li key={p}>{p}</li>)}</ul>
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="primary" onClick={() => void doRun()} disabled={run.isPending || save.isPending || !draft.code.trim()}>
                  {run.isPending ? <Spinner /> : <Play />}{run.isPending ? t("userscripts.running") : t("userscripts.run")}
                </Button>
                <Button onClick={() => void doSave().then((s) => s && toast(t("userscripts.saved")))} disabled={save.isPending || !dirty}>
                  <Save />{t("userscripts.save")}
                </Button>
                {draft.id && (
                  <Button variant="danger-ghost" onClick={() => setConfirm(true)} disabled={remove.isPending}>
                    <Trash2 />{t("userscripts.delete")}
                  </Button>
                )}
                <span className="ml-auto text-xs text-muted">
                  {dirty ? t("userscripts.unsaved") : saved ? t("userscripts.author", { author: saved.author, when: fmtRelative(saved.updated_at) }) : ""}
                </span>
              </div>
              <LastRun projectId={projectId} script={saved} />
            </section>
          )}
        </div>
      </div>
      <Confirm open={confirm} onOpenChange={setConfirm} danger
               title={t("userscripts.confirm_delete", { name: draft?.name ?? "" })} body={t("userscripts.lead")}
               confirmLabel={t("userscripts.delete")}
               onConfirm={() => draft?.id && remove.mutate(draft.id, {
                 onSuccess: () => { setDraft(null); toast(t("userscripts.deleted")); },
                 onError: (e) => toast.error(e.message),
               })} />
    </AppShell>
  );
}

function LastRun({ projectId, script }: { projectId: string; script: UserScript | undefined }) {
  const last = script?.last_run ?? null;
  return (
    <div className="space-y-2 border-t border-border pt-4">
      <h2 className="text-sm font-semibold">{t("userscripts.last_run")}</h2>
      {!last && <p className="text-sm text-muted">{t("userscripts.never_run")}</p>}
      {last && <p className="text-xs text-muted">{t(`userscripts.status_${last.status}`)} · {fmtRelative(last.at)}</p>}
      {last && last.status !== "started" && <CodeRun last={last} />}
      {last && last.status === "started" && <ScenarioRun projectId={projectId} runId={last.run_id} />}
    </div>
  );
}

function CodeRun({ last }: { last: Exclude<UserScriptRun, { status: "started" }> }) {
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted">{t("userscripts.run_of", { run: last.run_id })}</p>
      <AnalysisCard status={last.status} output={last.output} runtimeS={last.runtime_s} sandbox={last.sandbox}
                    stdoutTail={last.stdout_tail} stderrTail={last.stderr_tail} />
    </div>
  );
}

function ScenarioRun({ projectId, runId }: { projectId: string; runId: string }) {
  const run = useRun(runId);
  const navigate = useNavigate();
  const r = run.data;
  const busy = !r || r.status === "queued" || r.status === "running";
  const m = r?.result?.metrics;
  return (
    <div className="space-y-2 text-sm">
      <p className="flex items-center gap-2">
        {busy && <Spinner />}{t("userscripts.sim_status", { status: r?.status ?? "queued" })}
      </p>
      {r?.error && <p className="text-danger">{r.error}</p>}
      {m && (
        <ul className="flex flex-wrap gap-2">
          {m.evac_time_p95_s != null && <li className="rounded-full border border-border px-2.5 py-1 text-xs">{t("userscripts.evac", { t: fmtDuration(m.evac_time_p95_s) })}</li>}
          <li className="rounded-full border border-border px-2.5 py-1 text-xs">{t("userscripts.peak", { n: fmtNum(m.peak_density_ppm2, 1) })}</li>
        </ul>
      )}
      {!!r?.result?.notes.length && (
        <div>
          <p className="text-xs font-medium text-muted">{t("userscripts.sim_notes")}</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs">{r.result.notes.slice(0, 12).map((n) => <li key={n}>{n}</li>)}</ul>
        </div>
      )}
      {r && !busy && (
        <Button size="sm" onClick={() => { useUi.getState().setActiveRun(runId); navigate(`/p/${projectId}/expert/simulate`); }}>
          {t("userscripts.sim_open")}
        </Button>
      )}
    </div>
  );
}
