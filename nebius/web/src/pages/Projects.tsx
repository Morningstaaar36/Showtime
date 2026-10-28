/** "Your plans" (route `/projects`): every plan as a bright card, a search box and one clear way
 * to start a new plan. Samples and the one-sentence copilot sit below as more ways to start. */
import { ArrowUpRight, Building2, Check, Clock, Copy, Download, FolderOpen, Loader2, Map as MapIcon, MoreHorizontal, PencilLine, Plus, Search, Sparkles, Trash2, Trees, Upload, Users, Wand2 } from "lucide-react";
import type * as React from "react";
import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useCreateProject, useDeleteProject, useDuplicateProject, useImporters, useImportProject, useProjects, useTemplates } from "@/api/queries";
import type { ProjectSummary, Template, VenueDraft } from "@/api/types";
import { AppShell } from "@/app/AppHeader";
import { VenueThumb } from "@/components/VenueThumb";
import { Confirm } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input, Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { fmtInt, fmtRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CopilotBox } from "./Copilot";
import { DescribeTab } from "./newproject/DescribeTab";
import { acceptFor, typesText } from "@/lib/importTypes";

export function ProjectsPage() {
  const projects = useProjects();
  const templates = useTemplates();
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState<Template | null | "pick">(null);
  const importer = useImportProject();
  const fileRef = useRef<HTMLInputElement>(null);
  const kinds = useImporters().data?.importers ?? [];
  const importHint = t("projects.import_hint", { types: typesText(kinds) });
  const importAccept = acceptFor(kinds);
  const navigate = useNavigate();

  const all = useMemo(() => projects.data ?? [], [projects.data]);
  const items = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return ql ? all.filter((p) => p.name.toLowerCase().includes(ql) || p.venue_name.toLowerCase().includes(ql)) : all;
  }, [all, q]);
  const tplById = useMemo(() => new Map((templates.data ?? []).map((x) => [x.id, x])), [templates.data]);
  const empty = !!projects.data && all.length === 0;

  return (
    <AppShell className="bg-hero">
      <div className="mx-auto w-full max-w-6xl space-y-8 px-4 py-10">
        <section className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-3xl font-bold leading-tight tracking-tight sm:text-4xl">{t("projects.title")}</h1>
            <p className="mt-2 max-w-prose text-lg text-muted">{t("projects.lead")}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="lg" onClick={() => fileRef.current?.click()} disabled={importer.isPending} title={importHint}>
              <Upload />{t("projects.import")}
            </Button>
            {!empty && <Button size="lg" variant="primary" onClick={() => setCreating("pick")}><Plus />{t("projects.new")}</Button>}
            <input ref={fileRef} type="file" className="hidden" accept={importAccept} aria-label={importHint}
                   onChange={(e) => {
                     const f = e.target.files?.[0];
                     if (!f) return;
                     importer.mutate(f, {
                       onSuccess: (p) => { toast.success(t("projects.imported")); navigate(`/p/${p.id}`); },
                       onError: (err) => toast.error(err.message),
                     });
                     e.target.value = "";
                   }} />
          </div>
        </section>

        {all.length > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="relative w-full sm:max-w-sm">
              <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
              <Input type="search" aria-label={t("projects.search")} placeholder={t("projects.search_ph")} value={q}
                     onChange={(e) => setQ(e.target.value)} className="h-11 rounded-full pl-10 text-base shadow-sm" />
            </div>
            <p className="text-sm text-muted tabular">{all.length === 1 ? t("projects.count_one") : t("projects.count", { n: all.length })}</p>
          </div>
        )}

        {projects.isError && (
          <ErrorState title={t("projects.load_error")} message={(projects.error as Error).message}
                      hint={(projects.error as { hint?: string }).hint} onRetry={() => projects.refetch()} />
        )}
        {projects.isLoading && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-64" />)}</div>
        )}
        {empty && (
          <div className="flex flex-col items-center gap-4 rounded-[var(--radius-panel)] border-2 border-dashed border-border-strong bg-surface/80 px-6 py-12 text-center">
            <span className="grid size-14 place-items-center rounded-full bg-signal-soft text-signal [&_svg]:size-7"><FolderOpen aria-hidden /></span>
            <div>
              <p className="text-xl font-bold">{t("projects.empty_title")}</p>
              <p className="mx-auto mt-1 max-w-md text-muted">{t("projects.empty_body")}</p>
            </div>
            <Button variant="primary" size="lg" onClick={() => setCreating("pick")}><Plus />{t("projects.new")}</Button>
          </div>
        )}
        {all.length > 0 && items.length === 0 && (
          <div className="flex flex-wrap items-center gap-2 rounded-[var(--radius-panel)] border border-border bg-surface p-5">
            <p>{t("projects.no_match", { q: q.trim() })}</p>
            <Button variant="link" onClick={() => setQ("")}>{t("projects.clear_search")}</Button>
          </div>
        )}
        {items.length > 0 && (
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((p) => <li key={p.id}><ProjectCard p={p} template={p.template_id ? tplById.get(p.template_id) : undefined} /></li>)}
          </ul>
        )}

        <section aria-labelledby="more-h" className="space-y-4 pt-4">
          <h2 id="more-h" className="text-2xl font-bold tracking-tight">{t("projects.more_ways")}</h2>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <section aria-labelledby="samples-h" className="rounded-[var(--radius-panel)] border border-border bg-surface p-5 shadow-sm">
              <div className="flex items-start gap-3">
                <span className="grid size-11 shrink-0 place-items-center rounded-full bg-orange-soft text-orange [&_svg]:size-5"><Sparkles aria-hidden /></span>
                <div>
                  <h3 id="samples-h" className="text-lg font-semibold">{t("projects.samples_title")}</h3>
                  <p className="text-sm text-muted">{t("projects.samples_lead")}</p>
                </div>
              </div>
              <ul className="mt-4 grid grid-cols-2 gap-3">
                {(templates.data ?? [null, null, null, null]).map((tpl, i) => (
                  <li key={tpl?.id ?? i}>
                    {tpl ? (
                      <button type="button" onClick={() => setCreating(tpl)}
                              className="group flex h-full w-full flex-col overflow-hidden rounded-[var(--radius-control)] border-2 border-transparent bg-surface-2 text-left transition hover:-translate-y-0.5 hover:border-orange focus-visible:outline-2 focus-visible:outline-signal">
                        <span className="block h-20 w-full bg-orange-soft/60 p-2"><VenueThumb venue={tpl.venue} className="size-full" /></span>
                        <span className="flex flex-1 flex-col p-2.5">
                          <span className="text-sm font-semibold leading-snug">{tpl.name}</span>
                          <span className="mt-auto flex items-center gap-1 pt-1 text-xs text-muted tabular"><Users className="size-3.5" aria-hidden />{t("projects.people", { n: fmtInt(tpl.people) })}</span>
                        </span>
                      </button>
                    ) : <Skeleton className="h-32" />}
                  </li>
                ))}
              </ul>
            </section>
            <section aria-labelledby="copilot-h" className="rounded-[var(--radius-panel)] border border-border bg-surface p-5 shadow-sm">
              <div className="flex items-start gap-3">
                <span className="grid size-11 shrink-0 place-items-center rounded-full bg-pink-soft text-pink [&_svg]:size-5"><Wand2 aria-hidden /></span>
                <div>
                  <h3 id="copilot-h" className="text-lg font-semibold">{t("projects.copilot_title")}</h3>
                  <p className="text-sm text-muted">{t("projects.copilot_lead")}</p>
                </div>
              </div>
              <div className="mt-4"><CopilotBox /></div>
            </section>
          </div>
        </section>
      </div>
      <NewProjectDialog state={creating} onClose={() => setCreating(null)} templates={templates.data ?? []} />
    </AppShell>
  );
}

/** One plan: the whole card opens it; the menu holds copy, download and delete. */
function ProjectCard({ p, template }: { p: ProjectSummary; template?: Template }) {
  const del = useDeleteProject();
  const dup = useDuplicateProject();
  const [confirm, setConfirm] = useState(false);
  const navigate = useNavigate();
  const venue = p.thumb ?? template?.venue;
  const outdoor = p.mode === "outdoor";
  return (
    <article className="group relative flex h-full flex-col overflow-hidden rounded-[var(--radius-panel)] border-2 border-transparent bg-surface shadow-sm transition hover:-translate-y-0.5 hover:border-signal has-[a:focus-visible]:border-signal has-[a:focus-visible]:ring-4 has-[a:focus-visible]:ring-signal/20">
      <div className={cn("relative h-40 p-3", outdoor ? "bg-teal-soft/70" : "bg-sky-soft/70")}>
        {venue ? <VenueThumb venue={venue} className="size-full" />
          : <span className="grid size-full place-items-center text-line [&_svg]:size-10">{outdoor ? <Trees aria-hidden /> : <Building2 aria-hidden />}</span>}
        <span className="absolute left-3 top-3 inline-flex items-center gap-1 rounded-full bg-surface/90 px-2 py-0.5 text-xs font-medium text-ink shadow-sm">
          {outdoor ? <Trees className="size-3.5 text-teal" aria-hidden /> : <Building2 className="size-3.5 text-sky" aria-hidden />}
          {outdoor ? t("projects.outdoor") : t("projects.indoor")}
        </span>
        {p.sample && <span className="absolute right-3 top-3 rounded-full bg-signal px-2 py-0.5 text-xs font-semibold text-signal-ink shadow-sm">{t("projects.sample")}</span>}
      </div>
      <div className="flex flex-1 items-start gap-2 p-4">
        <div className="min-w-0 flex-1">
          <h3 className="line-clamp-2 text-base font-semibold leading-snug">
            {/* the link stretches over the whole card */}
            <Link to={`/p/${p.id}`} aria-label={t("projects.open", { name: p.name })}
                  className="outline-none after:absolute after:inset-0 group-hover:text-signal">{p.name}</Link>
          </h3>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
            <span className="inline-flex items-center gap-1 tabular"><Users className="size-4" aria-hidden />{t("projects.people", { n: fmtInt(p.people) })}</span>
            <span className="inline-flex items-center gap-1"><Clock className="size-4" aria-hidden />{t("projects.updated", { when: fmtRelative(p.updated_at) })}</span>
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={t("projects.actions", { name: p.name })}
                    className="relative z-10 -mr-2 -mt-1.5 size-11 shrink-0 text-muted hover:text-ink"><MoreHorizontal /></Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => navigate(`/p/${p.id}`)}><ArrowUpRight />{t("projects.menu_open")}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => dup.mutate(p.id, { onSuccess: () => toast.success(t("projects.duplicated")) })}><Copy />{t("projects.menu_copy")}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => { window.location.href = api.url(`/projects/${p.id}/export`); }}><Download />{t("projects.menu_download")}</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem danger onSelect={() => setConfirm(true)}><Trash2 />{t("projects.menu_delete")}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <Confirm open={confirm} onOpenChange={setConfirm} danger confirmLabel={t("projects.menu_delete")}
               title={t("projects.confirm_delete_title", { name: p.name })} body={t("projects.confirm_delete_body")}
               onConfirm={() => del.mutate(p.id, { onSuccess: () => toast.success(t("projects.deleted")) })} />
    </article>
  );
}

type Way = "describe" | "sample";

/** "New plan": the same three ways to start as Home. The map opens the full-page map; describe
 * and sample happen here, then the plan gets a name. */
function NewProjectDialog({ state, onClose, templates }: { state: Template | null | "pick"; onClose: () => void; templates: Template[] }) {
  return (
    <Dialog open={state !== null} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent wide className="max-h-[92vh] overflow-y-auto">
        {/* mounted only while open, so every opening starts fresh */}
        {state !== null && <NewPlanBody initial={state === "pick" ? null : state} templates={templates} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function NewPlanBody({ initial, templates, onClose }: { initial: Template | null; templates: Template[]; onClose: () => void }) {
  const create = useCreateProject();
  const navigate = useNavigate();
  const [way, setWay] = useState<Way | null>(initial ? "sample" : null);
  const [picked, setPicked] = useState<string | null>(initial?.id ?? null);
  const [name, setName] = useState("");
  const [draft, setDraft] = useState<VenueDraft | null>(null);
  const ready = way === "sample" ? !!picked : way === "describe" ? !!draft?.venue : false;
  const choose = (w: Way) => { setWay(w); setDraft(null); };
  const submit = () => {
    if (!ready || create.isPending) return;
    const body = way === "sample"
      ? { name, template_id: picked ?? undefined }
      : { name: name || draft?.venue?.name || "", venue: draft!.venue!, description: t("projects.from_description") };
    create.mutate(body, {
      onSuccess: (p) => { toast.success(t("projects.created")); onClose(); navigate(`/p/${p.id}/describe`); },
      onError: (e) => toast.error(e.message),
    });
  };
  return (
    <>
      <DialogHeader>
        <DialogTitle className="text-xl">{t("projects.create_title")}</DialogTitle>
        <DialogDescription className="text-base">{t("projects.create_lead")}</DialogDescription>
      </DialogHeader>
      <div role="group" aria-label={t("projects.ways")} className="grid gap-3 sm:grid-cols-3">
        <Link to="/new/place"
              className="group relative flex min-h-36 flex-col justify-between gap-3 overflow-hidden rounded-[var(--radius-panel)] bg-[linear-gradient(135deg,var(--sky),var(--signal))] p-4 text-white shadow-[var(--shadow-float)] transition hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal dark:bg-[linear-gradient(135deg,color-mix(in_srgb,var(--sky)_60%,black),color-mix(in_srgb,var(--signal)_70%,black))]">
          <span className="grid size-10 place-items-center rounded-full bg-white/20 [&_svg]:size-5"><MapIcon aria-hidden /></span>
          <span>
            <span className="block text-lg font-bold">{t("home.way_map")}</span>
            <span className="mt-0.5 block text-sm text-white/90">{t("home.way_map_lead")}</span>
          </span>
          <span className="absolute right-3 top-3 rounded-full bg-white/25 px-2.5 py-0.5 text-xs font-semibold">{t("home.recommended")}</span>
        </Link>
        <WayTile active={way === "describe"} onClick={() => choose("describe")} icon={<PencilLine aria-hidden />} tone="bg-pink-soft text-pink"
                 title={t("home.way_describe")} lead={t("home.way_describe_lead")} />
        <WayTile active={way === "sample"} onClick={() => choose("sample")} icon={<Sparkles aria-hidden />} tone="bg-orange-soft text-orange"
                 title={t("home.way_sample")} lead={t("home.way_sample_lead")} />
      </div>

      {way === "describe" && (
        <div className="animate-deal-in rounded-[var(--radius-panel)] border-2 border-pink/30 p-4"><DescribeTab onDraft={setDraft} /></div>
      )}
      {way === "sample" && (
        <fieldset className="animate-deal-in">
          <legend className="mb-2 font-semibold">{t("projects.pick_sample")}</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            {templates.map((tpl) => (
              <button key={tpl.id} type="button" aria-pressed={picked === tpl.id} onClick={() => setPicked(tpl.id)}
                      className={cn("flex min-h-11 gap-3 rounded-[var(--radius-panel)] border-2 p-3 text-left transition focus-visible:outline-2 focus-visible:outline-signal",
                        picked === tpl.id ? "border-orange bg-orange-soft/40" : "border-border hover:border-border-strong")}>
                <span className="block h-20 w-28 shrink-0 rounded-[var(--radius-control)] bg-orange-soft/60 p-1.5"><VenueThumb venue={tpl.venue} className="size-full" /></span>
                <span className="min-w-0">
                  <span className="flex items-center gap-1.5 font-semibold">{tpl.name}{picked === tpl.id && <Check className="size-4 shrink-0 text-orange" aria-hidden />}</span>
                  <span className="mt-0.5 line-clamp-2 text-sm text-muted">{tpl.description}</span>
                  <span className="mt-1 flex items-center gap-1 text-xs text-muted tabular"><Users className="size-3.5" aria-hidden />{t("projects.people", { n: fmtInt(tpl.people) })}</span>
                </span>
              </button>
            ))}
          </div>
        </fieldset>
      )}

      {way && (
        <div className="grid gap-1.5">
          <Label htmlFor="pname">{t("projects.create_name")}</Label>
          <Input id="pname" className="h-11 text-base" placeholder={draft?.venue?.name ?? t("projects.create_name_ph")} value={name}
                 onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") submit(); }} />
          <p className="text-xs text-muted">{t("projects.create_name_hint")}</p>
        </div>
      )}
      <DialogFooter className="items-center">
        {way === "describe" && !draft?.venue && <p className="mr-auto text-sm text-muted">{t("projects.describe_first")}</p>}
        <Button size="lg" onClick={onClose}>{t("common.cancel")}</Button>
        {way && (
          <Button size="lg" variant={ready ? "primary" : "secondary"} disabled={!ready || create.isPending} onClick={submit}>
            {create.isPending && <Loader2 className="animate-spin" />}{t("projects.create_button")}
          </Button>
        )}
      </DialogFooter>
    </>
  );
}

function WayTile({ active, onClick, icon, tone, title, lead }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; tone: string; title: string; lead: string;
}) {
  return (
    <button type="button" aria-pressed={active} onClick={onClick}
            className={cn("group flex min-h-36 flex-col justify-between gap-3 rounded-[var(--radius-panel)] border-2 bg-surface p-4 text-left shadow-sm transition hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal",
              active ? "border-signal ring-4 ring-signal-soft" : "border-border hover:border-border-strong")}>
      <span className={cn("grid size-10 place-items-center rounded-full [&_svg]:size-5", tone)}>{icon}</span>
      <span>
        <span className="block text-lg font-bold">{title}</span>
        <span className="mt-0.5 block text-sm text-muted">{lead}</span>
      </span>
    </button>
  );
}
