/** Write a real case from scratch (or from a copy of one) and save it next to the examples.
 * The designer builds the venue from the site description only, so the form asks for what it
 * needs: the crowd, the passages and their sizes, and where every number comes from. */
import { MapPin, Plus, Save, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { api, type ApiError } from "@/api/client";
import { useSaveRealCase } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Label, Textarea } from "@/components/ui/input";
import { t } from "@/i18n";
import { useEventKinds } from "@/lib/eventKinds";
import type { EventKindId } from "@/lib/venueOps";
import { cn } from "@/lib/utils";
import { type CaseFacts, fieldOfError, linesOf, missingField } from "./realCases";

const SELECT = "h-11 w-full rounded-[var(--radius-control)] border border-border bg-surface px-2 text-base";
const ZONES = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : ["UTC"];

interface Place { name: string; display_name: string; lat: number; lon: number }

/** `editId` set: change that saved case; else save a new one. */
export function CaseForm({ open, onOpenChange, initial, editId }: {
  open: boolean; onOpenChange: (v: boolean) => void; initial: CaseFacts; editId?: string;
}) {
  const [f, setF] = useState<CaseFacts>(initial);
  const [dims, setDims] = useState(initial.dimensions.join("\n"));
  const [approx, setApprox] = useState(initial.approximations.join("\n"));
  const [bad, setBad] = useState<{ field: string | null; message: string } | null>(null);
  const [found, setFound] = useState<string | null>(null);
  const [finding, setFinding] = useState(false);
  const { kinds } = useEventKinds();
  const save = useSaveRealCase();
  const set = <K extends keyof CaseFacts>(k: K, v: CaseFacts[K]) => setF((x) => ({ ...x, [k]: v }));
  const err = (field: string) => (bad?.field === field ? bad.message : null);

  const find = async () => {
    if (f.place.trim().length < 2) return;
    setFinding(true);
    try {
      const hits = await api.get<Place[]>(`/places/search?q=${encodeURIComponent(f.place.trim())}`);
      const hit = hits[0];
      if (!hit) { setFound(t("realcase.form.place_none")); return; }
      set("location", { ...f.location, lat: Math.round(hit.lat * 1e5) / 1e5, lon: Math.round(hit.lon * 1e5) / 1e5 });
      setFound(t("realcase.form.place_found", { name: hit.display_name || hit.name }));
    } catch (e) {
      setFound((e as Error).message);
    } finally {
      setFinding(false);
    }
  };

  const submit = () => {
    const facts: CaseFacts = { ...f, dimensions: linesOf(dims), approximations: linesOf(approx),
                               sources: f.sources.filter((s) => s.label.trim() || s.url.trim()) };
    const missing = missingField(facts);
    if (missing) { setBad({ field: missing, message: t(`realcase.form.need_${missing}`) }); return; }
    setBad(null);
    save.mutate({ id: editId, facts }, {
      onSuccess: (c) => { toast.success(t("realcase.form.saved", { title: c.title })); onOpenChange(false); },
      onError: (e) => setBad({ field: fieldOfError((e as ApiError).details), message: e.message }),
    });
  };

  const field = (id: keyof CaseFacts, label: string, input: React.ReactNode, hint?: string) => (
    <div className="grid gap-1.5">
      <Label htmlFor={`case-${id}`}>{label}</Label>
      {input}
      {hint && <p className="text-xs text-muted">{hint}</p>}
      {err(id) && <p role="alert" className="text-sm text-danger">{err(id)}</p>}
    </div>
  );
  const text = (id: "title" | "incident" | "place" | "toll", max: number, placeholder?: string) => (
    <Input id={`case-${id}`} value={f[id]} maxLength={max} placeholder={placeholder} aria-invalid={!!err(id)}
           onChange={(e) => set(id, e.target.value)} className="h-11 text-base" />
  );
  const num = (id: "deaths" | "people") => (
    <Input id={`case-${id}`} type="number" inputMode="numeric" min={0} value={f[id] || ""} aria-invalid={!!err(id)}
           onChange={(e) => set(id, Math.max(0, Math.round(Number(e.target.value) || 0)))} className="h-11 text-base" />
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent wide>
        <DialogHeader>
          <DialogTitle>{editId ? t("realcase.form.edit_title") : t("realcase.form.new_title")}</DialogTitle>
          <DialogDescription>{t("realcase.form.lead")}</DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <div className="grid gap-4 sm:grid-cols-2">
            {field("title", t("realcase.form.title"), text("title", 60), t("realcase.form.title_hint"))}
            {field("incident", t("realcase.form.incident"), text("incident", 160))}
            {field("date", t("realcase.form.date"),
              <Input id="case-date" type="date" value={f.date} onChange={(e) => set("date", e.target.value)} className="h-11 text-base" aria-invalid={!!err("date")} />)}
            {field("event_kind", t("realcase.form.kind"),
              <select id="case-event_kind" className={SELECT} value={f.event_kind} onChange={(e) => set("event_kind", e.target.value as EventKindId)}>
                {kinds.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
              </select>)}
          </div>

          <fieldset className="grid gap-2 rounded-[10px] border border-border p-3">
            <legend className="px-1 text-sm font-semibold">{t("realcase.form.where")}</legend>
            {field("place", t("realcase.form.place"),
              <div className="flex gap-2">
                {text("place", 160)}
                <Button type="button" variant="secondary" className="h-11 shrink-0" disabled={finding || f.place.trim().length < 2} onClick={find}>
                  <MapPin />{t("realcase.form.find")}
                </Button>
              </div>)}
            {found && <p className="text-xs text-muted" role="status">{found}</p>}
            <div className="grid grid-cols-3 gap-2">
              {(["lat", "lon"] as const).map((k) => (
                <div key={k} className="grid gap-1.5">
                  <Label htmlFor={`case-${k}`}>{t(`realcase.form.${k}`)}</Label>
                  <Input id={`case-${k}`} type="number" step="any" value={f.location[k]} className="h-11 text-base"
                         onChange={(e) => set("location", { ...f.location, [k]: Number(e.target.value) })} />
                </div>
              ))}
              <div className="grid gap-1.5">
                <Label htmlFor="case-tz">{t("realcase.form.timezone")}</Label>
                <Input id="case-tz" list="case-tz-list" value={f.location.timezone} className="h-11 text-base"
                       onChange={(e) => set("location", { ...f.location, timezone: e.target.value })} />
                <datalist id="case-tz-list">{ZONES.map((z) => <option key={z} value={z} />)}</datalist>
              </div>
            </div>
            {err("location") && <p role="alert" className="text-sm text-danger">{err("location")}</p>}
          </fieldset>

          <div className="grid gap-4 sm:grid-cols-3">
            {field("people", t("realcase.form.people"), num("people"), t("realcase.form.people_hint"))}
            {field("deaths", t("realcase.form.deaths"), num("deaths"))}
            {field("toll", t("realcase.form.toll"), text("toll", 200))}
          </div>

          {field("description", t("realcase.form.description"),
            <Textarea id="case-description" rows={6} maxLength={2000} value={f.description} aria-invalid={!!err("description")}
                      onChange={(e) => set("description", e.target.value)} className="text-base" />,
            t("realcase.form.description_hint", { n: f.description.length }))}
          <div className="grid gap-4 sm:grid-cols-2">
            {field("what_happened", t("realcase.form.what_happened"),
              <Textarea id="case-what_happened" rows={3} maxLength={300} value={f.what_happened} onChange={(e) => set("what_happened", e.target.value)} className="text-base" />)}
            {field("lesson", t("realcase.form.lesson"),
              <Textarea id="case-lesson" rows={3} maxLength={160} value={f.lesson} onChange={(e) => set("lesson", e.target.value)} className="text-base" />)}
          </div>

          <fieldset className={cn("grid gap-2 rounded-[10px] border p-3", err("sources") ? "border-danger" : "border-border")}>
            <legend className="px-1 text-sm font-semibold">{t("realcase.form.sources")}</legend>
            <p className="text-xs text-muted">{t("realcase.form.sources_hint")}</p>
            {f.sources.map((s, i) => (
              <div key={i} className="grid gap-2 sm:grid-cols-[1fr_1.4fr_auto]">
                <Input aria-label={t("realcase.form.source_label", { n: i + 1 })} placeholder={t("realcase.form.source_label_ph")} value={s.label} className="h-11 text-base"
                       onChange={(e) => set("sources", f.sources.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
                <Input aria-label={t("realcase.form.source_url", { n: i + 1 })} type="url" placeholder={t("realcase.form.source_url_ph")} value={s.url} className="h-11 text-base"
                       onChange={(e) => set("sources", f.sources.map((x, j) => (j === i ? { ...x, url: e.target.value } : x)))} />
                <Button type="button" variant="ghost" className="h-11" aria-label={t("realcase.form.source_remove", { n: i + 1 })}
                        disabled={f.sources.length === 1} onClick={() => set("sources", f.sources.filter((_, j) => j !== i))}><Trash2 /></Button>
              </div>
            ))}
            <Button type="button" variant="secondary" className="justify-self-start" disabled={f.sources.length >= 12}
                    onClick={() => set("sources", [...f.sources, { label: "", url: "" }])}><Plus />{t("realcase.form.source_add")}</Button>
            {err("sources") && <p role="alert" className="text-sm text-danger">{err("sources")}</p>}
          </fieldset>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="case-dimensions">{t("realcase.form.dimensions")}</Label>
              <Textarea id="case-dimensions" rows={4} value={dims} onChange={(e) => setDims(e.target.value)} className="text-base" />
              <p className="text-xs text-muted">{t("realcase.form.one_per_line")}</p>
              {err("dimensions") && <p role="alert" className="text-sm text-danger">{err("dimensions")}</p>}
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="case-approximations">{t("realcase.form.approximations")}</Label>
              <Textarea id="case-approximations" rows={4} value={approx} onChange={(e) => setApprox(e.target.value)} className="text-base" />
              <p className="text-xs text-muted">{t("realcase.form.one_per_line")}</p>
              {err("approximations") && <p role="alert" className="text-sm text-danger">{err("approximations")}</p>}
            </div>
          </div>

          {bad && !bad.field && <p role="alert" className="text-sm text-danger">{bad.message}</p>}
          {bad?.field && <p className="text-sm text-danger">{t("realcase.form.fix_marked")}</p>}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
            <Button type="submit" variant="primary" disabled={save.isPending}><Save />{t("realcase.form.save")}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
