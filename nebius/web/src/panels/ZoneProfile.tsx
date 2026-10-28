/** Who is in a crowd area (people groups), when they start moving and which route they walk; and
 * the venue's kind of event with its usual people mix. Each change is a saved patch. */
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ProjectDetail, Zone } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { t } from "@/i18n";
import { mixText, peopleKindLabel, useEventKinds } from "@/lib/eventKinds";
import { cn } from "@/lib/utils";
import { type EventKindId, setEventKindOp, zoneProfileOp } from "@/lib/venueOps";
import { displayNames } from "@/lib/venueText";
import { type GroupRow, groupsOf, kindsLeft, restPercent, routesOn, rowsOf, usualMixOps } from "@/lib/zoneProfile";
import { useVenueEdit } from "@/journey/useVenueEdit";

const SELECT = "h-10 rounded-[var(--radius-control)] border border-border bg-surface px-2 text-base disabled:opacity-60";

function PeopleMix({ zone, name, disabled, onSave }: {
  zone: Zone; name: string; disabled: boolean; onSave: (groups: NonNullable<Zone["groups"]>) => void;
}) {
  const saved = useMemo(() => rowsOf(zone.groups), [zone.groups]);
  const [rows, setRows] = useState<GroupRow[]>(saved);
  useEffect(() => setRows(saved), [saved]);
  const left = kindsLeft(rows);
  const parsed = groupsOf(rows);
  const dirty = JSON.stringify(rows) !== JSON.stringify(saved);
  return (
    <fieldset className="grid gap-2" disabled={disabled}>
      <legend className="text-sm font-semibold">{t("editor.profile.title")}</legend>
      <p className="text-xs text-muted">{t("editor.profile.lead")}</p>
      <ul className="grid gap-1.5">
        {rows.map((r, i) => {
          const label = peopleKindLabel(r.kind);
          return (
            <li key={r.kind} className="flex items-center gap-2">
              <Label htmlFor={`grp-${zone.id}-${r.kind}`} className="min-w-0 flex-1 truncate text-sm">{label}</Label>
              <Input id={`grp-${zone.id}-${r.kind}`} aria-label={t("editor.profile.share", { name: label })} type="number" inputMode="numeric"
                     min={0} max={100} step={5} value={r.percent} className="h-10 w-20 text-right text-base tabular"
                     onChange={(e) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, percent: e.target.value } : x)))} />
              <span className="text-sm text-muted">%</span>
              <Button type="button" variant="ghost" size="icon" aria-label={t("editor.profile.remove_group", { name: label })}
                      onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}><Trash2 /></Button>
            </li>
          );
        })}
      </ul>
      {left.length > 0 && (
        <div className="flex items-center gap-2">
          <Label htmlFor={`grp-add-${zone.id}`} className="sr-only">{t("editor.profile.add_group")}</Label>
          <select id={`grp-add-${zone.id}`} className={cn(SELECT, "flex-1")} value=""
                  onChange={(e) => e.target.value && setRows((rs) => [...rs, { kind: e.target.value as GroupRow["kind"], percent: "10" }])}>
            <option value="">{t("editor.profile.add_group")}…</option>
            {left.map((k) => <option key={k} value={k}>{peopleKindLabel(k)}</option>)}
          </select>
          <Plus className="size-4 text-muted" aria-hidden />
        </div>
      )}
      {"error" in parsed
        ? <p role="alert" className="text-sm text-danger">{t("editor.profile.over")}</p>
        : <p className="text-sm text-muted">{t("editor.profile.rest", { p: restPercent(rows) })}</p>}
      <Button type="button" variant="primary" size="sm" className="justify-self-start" disabled={!dirty || "error" in parsed}
              onClick={() => "groups" in parsed && onSave(parsed.groups)} aria-describedby={`mix-${zone.id}`}>
        {t("editor.profile.save")}
      </Button>
      <span id={`mix-${zone.id}`} className="sr-only">{name}</span>
    </fieldset>
  );
}

function StartDelay({ zone, usual, disabled, onSave }: {
  zone: Zone; usual: number | null; disabled: boolean; onSave: (s: number | null) => void;
}) {
  const custom = zone.pre_movement_s != null;
  const [text, setText] = useState(String(zone.pre_movement_s ?? usual ?? 60));
  useEffect(() => setText(String(zone.pre_movement_s ?? usual ?? 60)), [zone.pre_movement_s, usual]);
  const commit = () => {
    const n = Math.round(Number(text));
    if (Number.isFinite(n) && n >= 0 && n <= 3600 && n !== zone.pre_movement_s) onSave(n);
  };
  return (
    <fieldset className="grid gap-2" disabled={disabled}>
      <legend className="text-sm font-semibold">{t("editor.profile.start_title")}</legend>
      <div className="flex rounded-[var(--radius-control)] bg-surface-2 p-0.5">
        {([[false, t("editor.profile.start_default")], [true, t("editor.profile.start_custom")]] as const).map(([v, l]) => (
          <button key={String(v)} type="button" aria-pressed={custom === v}
                  onClick={() => { if (custom === v) return; if (v) onSave(Math.round(Number(text)) || 60); else onSave(null); }}
                  className={cn("min-h-10 flex-1 rounded-[6px] px-2 text-sm font-medium transition",
                                custom === v ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink")}>
            {l}
          </button>
        ))}
      </div>
      {custom && (
        <div className="flex items-center gap-2">
          <Label htmlFor={`pre-${zone.id}`} className="text-sm text-muted">{t("editor.profile.start_seconds")}</Label>
          <Input id={`pre-${zone.id}`} type="number" inputMode="numeric" min={0} max={3600} step={10} value={text}
                 onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === "Enter" && commit()}
                 className="h-10 w-24 text-right text-base tabular" />
          <span className="text-sm text-muted">{t("common.seconds")}</span>
        </div>
      )}
      {usual != null && <p className="text-xs text-muted">{t("editor.profile.start_usual", { s: usual })}</p>}
    </fieldset>
  );
}

/** Groups, start delay and route of one crowd area. */
export function ZoneProfileEditor({ project, zoneId, disabled }: { project: ProjectDetail; zoneId: string; disabled?: boolean }) {
  const venue = project.version.venue;
  const { submit, pending } = useVenueEdit(project.id);
  const { kinds } = useEventKinds();
  const floor = venue.floors.find((f) => f.zones.some((z) => z.id === zoneId));
  const zone = floor?.zones.find((z) => z.id === zoneId);
  const names = useMemo(() => displayNames(venue), [venue]);
  if (!floor || !zone) return null;
  const name = names.get(zone.id) ?? zone.id;
  const usual = kinds.find((k) => k.id === venue.event_kind)?.default_pre_movement_s ?? null;
  const routes = routesOn(venue, floor.floor_id);
  const off = !!disabled || pending;
  return (
    <div className="grid gap-5" data-testid="zone-profile">
      <PeopleMix zone={zone} name={name} disabled={off}
                 onSave={(groups) => submit([zoneProfileOp(zone.id, { groups })], t("editor.profile.saved", { name }))} />
      <StartDelay zone={zone} usual={usual} disabled={off}
                  onSave={(s) => submit([zoneProfileOp(zone.id, { pre_movement_s: s })], t("editor.profile.start_saved", { name }))} />
      <div className="grid gap-1.5">
        <Label htmlFor={`route-${zone.id}`} className="text-sm font-semibold">{t("editor.profile.route_title")}</Label>
        {routes.length ? (
          <select id={`route-${zone.id}`} className={SELECT} disabled={off} value={zone.route_id ?? ""}
                  onChange={(e) => submit([zoneProfileOp(zone.id, { route_id: e.target.value || null })], t("editor.profile.route_saved", { name }))}>
            <option value="">{t("editor.profile.route_none")}</option>
            {routes.map((r) => <option key={r.id} value={r.id}>{r.label || r.id}</option>)}
          </select>
        ) : <p className="text-sm text-muted">{t("editor.profile.no_routes")}</p>}
      </div>
    </div>
  );
}

/** Kind of event for the whole venue, and "Use the usual people mix in every area". */
export function EventKindControl({ project }: { project: ProjectDetail }) {
  const venue = project.version.venue;
  const { kinds, fromServer, loading } = useEventKinds();
  const { submit, pending } = useVenueEdit(project.id);
  const current = kinds.find((k) => k.id === venue.event_kind) ?? null;
  const mixOps = current ? usualMixOps(venue, current) : [];
  return (
    <section aria-labelledby="kind-title" className="grid gap-2" data-testid="event-kind">
      <Label id="kind-title" htmlFor="event-kind" className="text-base font-semibold">{t("editor.kinds.label")}</Label>
      <p className="text-sm text-muted">{t("editor.kinds.hint")}</p>
      <select id="event-kind" className={SELECT} disabled={pending || loading} value={venue.event_kind ?? ""}
              onChange={(e) => {
                const id = (e.target.value || null) as EventKindId | null;
                const label = kinds.find((k) => k.id === id)?.label ?? "";
                submit([setEventKindOp(id)], id ? t("editor.kinds.saved", { name: label }) : t("editor.kinds.cleared"));
              }}>
        <option value="">{t("editor.kinds.none")}</option>
        {kinds.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
      </select>
      {current && (
        <div className="grid gap-1 text-sm">
          <p className="text-muted">{current.description}</p>
          {current.default_groups.length > 0 && <p>{t("editor.kinds.usual_mix", { mix: mixText(current.default_groups) })}</p>}
          {current.default_pre_movement_s != null && <p>{t("editor.kinds.usual_start", { s: current.default_pre_movement_s })}</p>}
        </div>
      )}
      {current && (current.default_groups.length > 0 || current.default_pre_movement_s != null) && (
        <Button variant="secondary" className="justify-self-start" disabled={pending || !mixOps.length}
                onClick={() => submit(mixOps, t("editor.kinds.apply_mix_done", { n: mixOps.length }))}>
          {t("editor.kinds.apply_mix")}
        </Button>
      )}
      {!fromServer && !loading && <p className="text-xs text-muted">{t("editor.kinds.offline")}</p>}
    </section>
  );
}
