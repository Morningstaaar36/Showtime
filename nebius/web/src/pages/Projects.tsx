import { ArrowUpRight, Building2, Copy, Download, FolderOpen, LayoutTemplate, Map as MapIcon, MoreHorizontal, Plus, Search, Sparkles, Trash2, Trees, Upload, Users } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useCreateProject, useDeleteProject, useDuplicateProject, useImportProject, useProjects, useTemplates } from "@/api/queries";
import type { ProjectSummary, Template, VenueDraft } from "@/api/types";
import { AppHeader } from "@/app/AppHeader";
import { VenueThumb } from "@/components/VenueThumb";
import { Confirm } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input, Label } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { fmtInt, fmtRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CopilotBox } from "./Copilot";
import { DescribeTab } from "./newproject/DescribeTab";
import { MapTab } from "./newproject/MapTab";

export function ProjectsPage() {
  const projects = useProjects();
  const templates = useTemplates();
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState<Template | null | "pick">(null);
  const importer = useImportProject();
  const fileRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const items = useMemo(() => {
    const all = projects.data ?? [];
    const ql = q.trim().toLowerCase();
    return ql ? all.filter((p) => p.name.toLowerCase().includes(ql) || p.venue_name.toLowerCase().includes(ql)) : all;
  }, [projects.data, q]);
  const tplById = useMemo(() => new Map((templates.data ?? []).map((x) => [x.id, x])), [templates.data]);

  return (
    <div className="min-h-full">
      <AppHeader />
      <main id="main" className="mx-auto max-w-6xl px-4 pb-16">
        <section className="relative mt-8 overflow-hidden rounded-[14px] border border-border bg-surface">
          <div className="drafting-grid absolute inset-0 opacity-60" aria-hidden />
          <div className="relative grid gap-6 p-6 md:grid-cols-[1.45fr_1fr] md:items-center md:p-8">
            <div>
              <p className="text-sm font-medium text-signal">Event Copilot · crowd-safety planning</p>
              <h1 className="mt-2 text-balance text-3xl font-semibold leading-tight tracking-tight">From one sentence to a crowd-safety plan you can defend.</h1>
              <p className="mt-3 max-w-prose text-muted">
                Say what, where, when and how many. Showtime pulls the real site from the map, lays out the event,
                estimates capacity, staff, toilets and budget, simulates the crowd, and lets AI red and blue teams break
                and fix the plan, down to the latest safe time to start evacuating.
              </p>
              <div className="mt-5"><CopilotBox /></div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button onClick={() => setCreating("pick")}><Plus />{t("projects.new")}</Button>
                <Button onClick={() => fileRef.current?.click()} disabled={importer.isPending}><Upload />{t("common.import")}</Button>
                <input ref={fileRef} type="file" className="hidden" accept=".zip,.json,.dxf"
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
            </div>
            <ul className="grid gap-3 text-sm">
              {[["1", "Real site or your words", "OpenStreetMap buildings, parks and roads, or a venue designed from a description"],
                ["2", "Plan for the day", "Safe capacity, exits, stewards, first aid, toilets and budget, each with its source"],
                ["3", "Simulate and red-team", "Crowd simulation, AI attacks from real incidents, measured fixes, evacuation deadline"]].map(([n, a, b]) => (
                <li key={n} className="flex gap-3 rounded-[10px] border border-border bg-surface/90 p-3">
                  <span className="grid size-6 shrink-0 place-items-center rounded-full bg-signal-soft text-xs font-semibold text-signal tabular">{n}</span>
                  <div><p className="font-medium leading-snug">{a}</p><p className="mt-0.5 text-xs text-muted">{b}</p></div>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <div className="mt-10 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-semibold tracking-tight">{t("projects.title")}</h2>
          <div className="relative w-full max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <Input aria-label={t("projects.search")} placeholder={t("projects.search")} value={q}
                   onChange={(e) => setQ(e.target.value)} className="pl-9" />
          </div>
        </div>

        {projects.isError && (
          <ErrorState className="mt-4" title={t("projects.load_error")} message={(projects.error as Error).message}
                      hint={(projects.error as { hint?: string }).hint} onRetry={() => projects.refetch()} />
        )}
        {projects.isLoading && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-64" />)}
          </div>
        )}
        {projects.data && items.length === 0 && !q && (
          <EmptyState className="mt-4" icon={<FolderOpen />} title={t("projects.empty_title")} body={t("projects.empty_body")}>
            <Button variant="primary" onClick={() => setCreating("pick")}><Plus />{t("projects.new")}</Button>
          </EmptyState>
        )}
        {projects.data && items.length === 0 && q && (
          <p className="mt-6 text-sm text-muted">No project matches “{q}”.</p>
        )}
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((p) => <ProjectCard key={p.id} p={p} template={p.template_id ? tplById.get(p.template_id) : undefined} />)}
        </div>

        <section className="mt-12">
          <h2 className="text-xl font-semibold tracking-tight">{t("projects.create_pick")}</h2>
          <p className="mt-1 text-sm text-muted">Each template is a complete, validated venue you can edit.</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {(templates.data ?? []).map((tpl) => (
              <button key={tpl.id} type="button" onClick={() => setCreating(tpl)}
                      className="group rounded-[10px] border border-border bg-surface p-3 text-left transition hover:-translate-y-0.5 hover:border-border-strong hover:shadow-[var(--shadow-float)]">
                <div className="aspect-[4/3] rounded-[6px] bg-plan p-2"><VenueThumb venue={tpl.venue} className="size-full" /></div>
                <p className="mt-3 font-medium">{tpl.name}</p>
                <p className="mt-0.5 line-clamp-2 text-xs text-muted">{tpl.description}</p>
                <p className="mt-2 flex items-center gap-1.5 text-xs text-muted tabular"><Users className="size-3.5" />{fmtInt(tpl.people)}</p>
              </button>
            ))}
            {templates.isLoading && [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-56" />)}
          </div>
        </section>
      </main>
      <NewProjectDialog state={creating} onClose={() => setCreating(null)} templates={templates.data ?? []} />
    </div>
  );
}

function ProjectCard({ p, template }: { p: ProjectSummary; template?: Template }) {
  const del = useDeleteProject();
  const dup = useDuplicateProject();
  const [confirm, setConfirm] = useState(false);
  const navigate = useNavigate();
  return (
    <article className="group relative flex flex-col rounded-[10px] border border-border bg-surface transition hover:border-border-strong hover:shadow-[var(--shadow-float)]">
      <Link to={`/p/${p.id}`} className="block rounded-t-[10px] bg-plan p-3" aria-label={`Open ${p.name}`}>
        <div className="aspect-[16/9]">{p.thumb ? <VenueThumb venue={p.thumb} className="size-full" /> : template ? <VenueThumb venue={template.venue} className="size-full" /> :
          <div className="grid size-full place-items-center text-line">{p.mode === "indoor" ? <Building2 /> : <Trees />}</div>}</div>
      </Link>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <Link to={`/p/${p.id}`} className="min-w-0">
            <h3 className="truncate font-semibold group-hover:text-signal">{p.name}</h3>
            <p className="truncate text-xs text-muted">{p.venue_name} · v{p.current_version}</p>
          </Link>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Project actions"><MoreHorizontal /></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => navigate(`/p/${p.id}`)}><ArrowUpRight />{t("common.open")}</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => dup.mutate(p.id, { onSuccess: () => toast.success(t("projects.duplicated")) })}><Copy />{t("common.duplicate")}</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => { window.location.href = api.url(`/projects/${p.id}/export`); }}><Download />{t("common.export")}</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem danger onSelect={() => setConfirm(true)}><Trash2 />{t("common.delete")}</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div className="mt-auto flex flex-wrap items-center gap-1.5">
          {p.sample && <Badge tone="signal">{t("projects.sample")}</Badge>}
          <Badge tone="outline">{p.mode === "indoor" ? t("projects.indoor") : t("projects.outdoor")}</Badge>
          <Badge tone="neutral"><Users />{fmtInt(p.people)}</Badge>
          <Badge tone="neutral">{p.exits} exits</Badge>
          <span className="ml-auto text-xs text-muted">{fmtRelative(p.updated_at)}</span>
        </div>
      </div>
      <Confirm open={confirm} onOpenChange={setConfirm} danger confirmLabel={t("common.delete")}
               title={t("projects.confirm_delete_title", { name: p.name })} body={t("projects.confirm_delete_body")}
               onConfirm={() => del.mutate(p.id, { onSuccess: () => toast.success(t("projects.deleted")) })} />
    </article>
  );
}

function NewProjectDialog({ state, onClose, templates }: { state: Template | null | "pick"; onClose: () => void; templates: Template[] }) {
  const create = useCreateProject();
  const navigate = useNavigate();
  const [picked, setPicked] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [tab, setTab] = useState<"template" | "describe" | "map">("template");
  const [draft, setDraft] = useState<VenueDraft | null>(null);
  const open = state !== null;
  const current = picked ?? (state && state !== "pick" ? state.id : templates[0]?.id ?? null);
  const close = () => { onClose(); setPicked(null); setName(""); setDraft(null); setTab("template"); };
  const canCreate = tab === "template" ? !!current : !!draft?.venue;
  const submit = () => {
    const body = tab === "template"
      ? { name, template_id: current ?? undefined }
      : { name: name || draft?.venue?.name || "", venue: draft!.venue!,
          description: tab === "map" ? "Imported from OpenStreetMap" : "Designed from a description" };
    create.mutate(body, {
      onSuccess: (p) => { toast.success(t("projects.created")); close(); navigate(`/p/${p.id}/describe`); },
      onError: (e) => toast.error(e.message),
    });
  };
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) close(); }}>
      <DialogContent wide className="max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("projects.create_title")}</DialogTitle>
          <DialogDescription>Start from a template, describe your venue in words, or pick a real place on the map. You can edit everything afterwards, by typing or by dragging in 3D.</DialogDescription>
        </DialogHeader>
        <Tabs value={tab} onValueChange={(v) => { setTab(v as typeof tab); setDraft(null); }}>
          <TabsList className="w-full">
            <TabsTrigger value="template"><LayoutTemplate className="mr-1.5 inline size-4" />Template</TabsTrigger>
            <TabsTrigger value="describe"><Sparkles className="mr-1.5 inline size-4" />Describe it</TabsTrigger>
            <TabsTrigger value="map"><MapIcon className="mr-1.5 inline size-4" />Real place</TabsTrigger>
          </TabsList>
          <TabsContent value="template" className="pt-4">
            <div className="grid gap-3 sm:grid-cols-2">
              {templates.map((tpl) => (
                <button key={tpl.id} type="button" onClick={() => setPicked(tpl.id)}
                        className={cn("flex gap-3 rounded-[10px] border p-3 text-left transition",
                          current === tpl.id ? "border-signal bg-signal-soft/50 ring-2 ring-signal/20" : "border-border hover:border-border-strong")}>
                  <div className="h-20 w-28 shrink-0 rounded-[6px] bg-plan p-1.5"><VenueThumb venue={tpl.venue} className="size-full" /></div>
                  <div className="min-w-0">
                    <p className="font-medium">{tpl.name}</p>
                    <p className="mt-0.5 line-clamp-3 text-xs text-muted">{tpl.description}</p>
                  </div>
                </button>
              ))}
            </div>
          </TabsContent>
          <TabsContent value="describe" className="pt-4"><DescribeTab onDraft={setDraft} /></TabsContent>
          <TabsContent value="map" className="pt-4" forceMount hidden={tab !== "map"}><MapTab onDraft={setDraft} /></TabsContent>
        </Tabs>
        <div className="grid gap-1.5">
          <Label htmlFor="pname">{t("projects.create_name")}</Label>
          <Input id="pname" placeholder={draft?.venue?.name ?? t("projects.create_name_ph")} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <DialogFooter>
          <Button onClick={close}>{t("common.cancel")}</Button>
          <Button variant="primary" disabled={!canCreate || create.isPending} onClick={submit}>
            {t("projects.create_button")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
