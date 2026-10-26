/** Organizer policy and operational proposals, backed by the shared atomic plan API. */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { qk, usePlan } from "@/api/queries";
import type { EditResult } from "@/api/types";
import type { BundlePreview, ObjectConstraint, PlanAction, PlanBundle, PlanData, PlanSnapshot } from "@/types/generated";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";

const csv = (s: string) => s.split(",").map((v) => v.trim()).filter(Boolean);
const selectClass = "min-h-10 w-full rounded border border-border bg-surface px-2 text-sm";
const defaultPolicy = (): ObjectConstraint => ({ locked: false, placement: "movable", origin: "existing", access: "allowed", required_approvals: [], estimated_cost: null });

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block space-y-1 text-sm"><span>{label}</span>{children}</label>;
}

export function OperationalPlan({ projectId }: { projectId: string }) {
  const query = usePlan(projectId);
  return <details className="rounded-lg border border-border p-3" data-testid="operational-plan">
    <summary className="cursor-pointer font-semibold">{t("ui.planeditor.resources_and_operational_plan")}</summary>
    {query.isError ? <ErrorState message={query.error.message} onRetry={() => query.refetch()} />
      : query.data ? <PlanEditor key={query.data.version} snapshot={query.data} /> : <p>{t("ui.planeditor.loading_plan")}</p>}
  </details>;
}

function PlanEditor({ snapshot }: { snapshot: PlanSnapshot }) {
  const [draft, setDraft] = useState<PlanData>(() => structuredClone(snapshot.plan));
  const [resourceId, setResourceId] = useState("");
  const [approvalId, setApprovalId] = useState("");
  const [error, setError] = useState("");
  const qc = useQueryClient();
  const base = `/projects/${snapshot.project_id}`;
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["plan", snapshot.project_id] });
    void qc.invalidateQueries({ queryKey: qk.project(snapshot.project_id) });
    void qc.invalidateQueries({ queryKey: qk.versions(snapshot.project_id) });
    void qc.invalidateQueries({ queryKey: qk.runs(snapshot.project_id) });
    void qc.invalidateQueries({ queryKey: ["countdown", snapshot.project_id] });
  };
  const save = useMutation({ mutationFn: () => api.put<EditResult>(`${base}/plan`, { expected_version: snapshot.version, plan: draft }), onSuccess: invalidate, onError: (e) => setError(e.message) });
  const change = (fn: (next: PlanData) => void) => { const next = structuredClone(draft); fn(next); setDraft(next); setError(""); };
  const dirty = JSON.stringify(draft) !== JSON.stringify(snapshot.plan);
  const objects = snapshot.venue.floors.flatMap((f) => [{ id: f.floor_id, label: f.name || f.floor_id }, ...f.exits, ...f.obstacles, ...f.zones]).concat(snapshot.venue.stairs.map((s) => ({ id: s.id, label: s.id })));

  return <div className="mt-3 space-y-4">
    <p className="text-xs text-muted">{t("ui.planeditor.saved_version_note", { n: snapshot.version })}</p>
    <fieldset className="space-y-2"><legend className="font-medium">{t("ui.planeditor.allowed_changes")}</legend>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.enforce_constraints} onChange={(e) => change((n) => { n.enforce_constraints = e.target.checked; })} />{t("ui.planeditor.enforce_organizer_constraints")}</label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.constraints.allow_construction} onChange={(e) => change((n) => { n.constraints.allow_construction = e.target.checked; })} />{t("ui.planeditor.construction_allowed_with_recorded_approval")}</label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.constraints.require_staff_for_measures} onChange={(e) => change((n) => { n.constraints.require_staff_for_measures = e.target.checked; })} />{t("ui.planeditor.require_staff_for_operational_measures")}</label>
      <Field label="Permitted edit operations (comma separated; blank allows registered edits)"><Input value={draft.constraints.allowed_ops?.join(", ") ?? ""} onChange={(e) => change((n) => { n.constraints.allowed_ops = e.target.value.trim() ? csv(e.target.value) : null; })} /></Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Declared cost budget"><Input type="number" min="0" value={draft.constraints.budget_limit ?? ""} onChange={(e) => change((n) => { n.constraints.budget_limit = e.target.value === "" ? null : Number(e.target.value); })} /></Field>
        <Field label="Currency"><Input maxLength={3} value={draft.constraints.currency} onChange={(e) => change((n) => { n.constraints.currency = e.target.value.toUpperCase(); })} /></Field>
      </div>
      <p className="text-xs text-muted">{t("ui.planeditor.cost_figures_are_declared_estimates")}</p>
    </fieldset>

    <fieldset className="space-y-2"><legend className="font-medium">{t("ui.planeditor.staff_and_equipment")}</legend>
      {Object.entries(draft.constraints.resources).map(([id, r]) => <div key={id} className="space-y-2 rounded border border-border p-2">
        <div className="flex items-center justify-between"><strong className="text-sm">{id}</strong><Button size="sm" variant="ghost" onClick={() => change((n) => { delete n.constraints.resources[id]; })}>{t("ui.planeditor.remove_resource")}</Button></div>
        <div className="grid grid-cols-2 gap-2"><Field label={`${id} kind`}><select className={selectClass} value={r.kind} onChange={(e) => change((n) => { n.constraints.resources[id].kind = e.target.value as "staff" | "equipment"; })}><option value="staff">{t("ui.planeditor.staff")}</option><option value="equipment">{t("ui.planeditor.equipment")}</option></select></Field>
        <Field label={`${id} count`}><Input type="number" min="0" step="1" value={r.count} onChange={(e) => change((n) => { n.constraints.resources[id].count = Number(e.target.value); })} /></Field>
        <Field label={t("ui.planeditor.available_from", { id })}><Input type="number" min="0" value={r.available_from_s} onChange={(e) => change((n) => { n.constraints.resources[id].available_from_s = Number(e.target.value); })} /></Field>
        <Field label={t("ui.planeditor.available_until", { id })}><Input type="number" min="1" value={r.available_until_s} onChange={(e) => change((n) => { n.constraints.resources[id].available_until_s = Number(e.target.value); })} /></Field></div>
      </div>)}
      <div className="flex gap-2"><Input aria-label={t("ui.planeditor.new_resource_id")} placeholder={t("ui.planeditor.stewards_or_radios")} value={resourceId} onChange={(e) => setResourceId(e.target.value)} /><Button disabled={!resourceId.trim() || !!draft.constraints.resources[resourceId.trim()]} onClick={() => { change((n) => { n.constraints.resources[resourceId.trim()] = { kind: "staff", count: 1, available_from_s: 0, available_until_s: 3600 }; }); setResourceId(""); }}>{t("ui.planeditor.add_resource")}</Button></div>
    </fieldset>

    <fieldset className="space-y-2"><legend className="font-medium">{t("ui.planeditor.permissions")}</legend>
      {Object.entries(draft.constraints.approvals).map(([id, a]) => <div key={id} className="space-y-2 rounded border border-border p-2">
        <div className="flex items-center justify-between"><strong className="text-sm">{id}</strong><Button size="sm" variant="ghost" onClick={() => change((n) => { delete n.constraints.approvals[id]; })}>{t("ui.planeditor.remove_permission")}</Button></div>
        <Field label={`${id} status`}><select className={selectClass} value={a.status} onChange={(e) => change((n) => { n.constraints.approvals[id].status = e.target.value as typeof a.status; })}><option value="pending">{t("ui.planeditor.pending")}</option><option value="approved">{t("ui.planeditor.approved")}</option><option value="rejected">{t("ui.planeditor.rejected")}</option></select></Field>
        <Field label={`${id} source`}><Input value={a.source} onChange={(e) => change((n) => { n.constraints.approvals[id].source = e.target.value; })} /></Field>
        <Field label={t("ui.planeditor.recorded_by", { id })}><Input value={a.recorded_by} onChange={(e) => change((n) => { n.constraints.approvals[id].recorded_by = e.target.value; })} /></Field>
      </div>)}
      <div className="flex gap-2"><Input aria-label={t("ui.planeditor.new_permission_id")} placeholder={t("ui.planeditor.venue_permission")} value={approvalId} onChange={(e) => setApprovalId(e.target.value)} /><Button disabled={!approvalId.trim() || !!draft.constraints.approvals[approvalId.trim()]} onClick={() => { change((n) => { n.constraints.approvals[approvalId.trim()] = { status: "pending", source: "", recorded_by: "" }; }); setApprovalId(""); }}>{t("ui.planeditor.add_permission")}</Button></div>
    </fieldset>

    <details><summary className="cursor-pointer text-sm font-medium">{t("ui.planeditor.object_constraints")}</summary><div className="mt-2 space-y-2">{objects.map((obj) => {
      const p = draft.constraints.objects[obj.id] ?? defaultPolicy();
      const policy = (values: Partial<ObjectConstraint>) => change((n) => { n.constraints.objects[obj.id] = { ...p, ...values }; });
      return <div key={obj.id} className="space-y-2 rounded border border-border p-2">
        <strong className="text-sm">{obj.label || obj.id} ({obj.id})</strong>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" aria-label={`Lock ${obj.id}`} checked={p.locked} onChange={(e) => policy({ locked: e.target.checked })} />{t("ui.planeditor.locked")}</label>
        <div className="grid grid-cols-2 gap-2">
          <Field label={`${obj.id} placement`}><select className={selectClass} value={p.placement} onChange={(e) => policy({ placement: e.target.value as typeof p.placement })}><option value="movable">{t("ui.planeditor.movable")}</option><option value="fixed">{t("ui.planeditor.fixed")}</option></select></Field>
          <Field label={`${obj.id} origin`}><select className={selectClass} value={p.origin} onChange={(e) => policy({ origin: e.target.value as typeof p.origin })}><option value="existing">{t("ui.planeditor.existing")}</option><option value="proposed">{t("ui.planeditor.proposed_construction")}</option></select></Field>
          <Field label={`${obj.id} access`}><select className={selectClass} value={p.access} onChange={(e) => policy({ access: e.target.value as typeof p.access })}><option value="allowed">{t("ui.planeditor.allowed")}</option><option value="restricted">{t("ui.planeditor.needs_permission")}</option><option value="unavailable">{t("ui.planeditor.unavailable")}</option></select></Field>
          <Field label={t("ui.planeditor.obj_cost", { id: obj.id })}><Input type="number" min="0" value={p.estimated_cost ?? ""} onChange={(e) => policy({ estimated_cost: e.target.value === "" ? null : Number(e.target.value) })} /></Field>
        </div>
        <Field label={t("ui.planeditor.obj_permissions", { id: obj.id })}><Input value={p.required_approvals.join(", ")} onChange={(e) => policy({ required_approvals: csv(e.target.value) })} /></Field>
      </div>;
    })}</div></details>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    <Button variant="primary" disabled={save.isPending || (snapshot.configured && !dirty)} onClick={() => save.mutate()}>{t("ui.planeditor.save_organizer_settings")}</Button>
    {!snapshot.configured || dirty ? <p className="text-sm text-muted">{t("ui.planeditor.save_settings_to_enable_action")}</p> : <ActionEditor snapshot={snapshot} onApplied={invalidate} />}
  </div>;
}

function ActionEditor({ snapshot, onApplied }: { snapshot: PlanSnapshot; onApplied: () => void }) {
  const [editing, setEditing] = useState("");
  const [id, setId] = useState("");
  const [label, setLabel] = useState("");
  const [type, setType] = useState("staggered_release");
  const [target, setTarget] = useState(snapshot.venue.floors[0]?.zones[0]?.id ?? "");
  const [destination, setDestination] = useState("");
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(60);
  const [delay, setDelay] = useState(20);
  const [fraction, setFraction] = useState(0.4);
  const [dependencies, setDependencies] = useState("");
  const [permissions, setPermissions] = useState("");
  const [cost, setCost] = useState("");
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [preview, setPreview] = useState<{ body: PlanBundle; result: BundlePreview } | null>(null);
  const [error, setError] = useState("");
  const path = `/projects/${snapshot.project_id}/plan/bundles`;
  const test = useMutation({ mutationFn: (body: PlanBundle) => api.post<BundlePreview>(`${path}/preview`, body), onSuccess: (result, body) => { setPreview({ body, result }); setError(""); }, onError: (e) => { setPreview(null); setError(e.message); } });
  const apply = useMutation({ mutationFn: (body: PlanBundle) => api.post<EditResult>(path, body), onSuccess: onApplied, onError: (e) => { setPreview(null); setError(e.message); } });
  const exits = snapshot.venue.floors.flatMap((f) => f.exits);
  const zones = snapshot.venue.floors.flatMap((f) => f.zones);
  const targets = type === "staggered_release" ? zones : exits;
  const bundle = (action?: PlanAction, remove?: string): PlanBundle => ({ expected_version: snapshot.version, patch: { schema_version: 1, ops: [] }, actions: action && !editing ? [action] : [], replace_actions: action && editing ? [action] : [], remove_action_ids: remove ? [remove] : [], new_objects: {}, message: remove ? `Remove ${remove}` : `Save operational action ${id}`, source: "user" } as PlanBundle);
  const load = (action: PlanAction) => {
    const ev = action.event as Record<string, unknown> | null;
    setEditing(action.action_id); setId(action.action_id); setLabel(action.label);
    setType(String(ev?.type ?? "note")); setTarget(String(ev?.zone_id ?? ev?.exit_id ?? ev?.from_exit_id ?? ""));
    setDestination(String(ev?.to_exit_id ?? "")); setStart(action.start_s); setEnd(action.end_s);
    setDelay(Number(ev?.delay_s ?? 20)); setFraction(Number(ev?.fraction ?? 0.4));
    setDependencies(action.depends_on.join(", ")); setPermissions(action.required_approvals.join(", "));
    setCost(action.estimated_cost == null ? "" : String(action.estimated_cost));
    setQuantities(Object.fromEntries(action.resources.map((r) => [r.resource_id, r.quantity]))); setPreview(null);
  };
  const propose = () => {
    const event = type === "note" ? null : type === "staggered_release" ? { type, at_s: start, zone_id: target, delay_s: delay }
      : type === "one_way" ? { type, at_s: start, exit_id: target }
      : { type, at_s: start, from_exit_id: target, to_exit_id: destination, fraction };
    test.mutate(bundle({ action_id: id.trim(), label, event, start_s: start, end_s: end,
      target_ids: [], depends_on: csv(dependencies), required_approvals: csv(permissions),
      resources: Object.entries(quantities).filter(([, n]) => n > 0).map(([resource_id, quantity]) => ({ resource_id, quantity })),
      source: "user", estimated_cost: cost === "" ? null : Number(cost) } as PlanAction));
  };
  return <section className="space-y-3 border-t border-border pt-3" aria-label={t("ui.planeditor.operational_actions")}>
    <h3 className="font-medium">{t("ui.planeditor.operational_actions")}</h3>
    {snapshot.plan.actions.length === 0 ? <p className="text-sm text-muted">{t("ui.planeditor.no_saved_actions")}</p> : <ul className="space-y-2">{snapshot.plan.actions.map((a) => <li key={a.action_id} className="rounded border border-border p-2 text-sm">
      <ActionDetails action={a} />
      <div className="mt-2 flex gap-2"><Button size="sm" disabled={a.event != null && !["staggered_release", "one_way", "marshal_redirect"].includes(a.event.type)} onClick={() => load(a)}>{t("ui.planeditor.edit_action")}</Button><Button size="sm" onClick={() => test.mutate(bundle(undefined, a.action_id))}>{t("ui.planeditor.preview_removal")}</Button></div>
    </li>)}</ul>}
    <fieldset className="space-y-2" onChange={() => setPreview(null)}>
      <legend className="font-medium">{editing ? `Replace ${editing}` : t("ui.planeditor.propose_an_action")}</legend>
      {editing && <Button size="sm" onClick={() => { setEditing(""); setId(""); setPreview(null); }}>{t("ui.planeditor.create_another_action")}</Button>}
      <Field label="Action ID"><Input value={id} disabled={!!editing} onChange={(e) => setId(e.target.value)} /></Field>
      <Field label="Action description"><Textarea value={label} onChange={(e) => setLabel(e.target.value)} /></Field>
      <Field label="Measure"><select className={selectClass} value={type} onChange={(e) => { setType(e.target.value); setTarget(e.target.value === "staggered_release" ? zones[0]?.id ?? "" : exits[0]?.id ?? ""); }}><option value="staggered_release">{t("ui.planeditor.staggered_release")}</option><option value="one_way">{t("ui.planeditor.one_way_exit")}</option><option value="marshal_redirect">{t("ui.planeditor.marshal_redirect")}</option><option value="note">{t("ui.planeditor.checklist_task_no_simulation_effect")}</option></select></Field>
      {type !== "note" && <Field label="Action target"><select className={selectClass} value={target} onChange={(e) => setTarget(e.target.value)}>{targets.map((o) => <option key={o.id} value={o.id}>{o.label || o.id}</option>)}</select></Field>}
      {type === "marshal_redirect" && <><Field label="Destination exit"><select className={selectClass} value={destination} onChange={(e) => setDestination(e.target.value)}><option value="">{t("ui.planeditor.select_exit")}</option>{exits.map((o) => <option key={o.id} value={o.id}>{o.label || o.id}</option>)}</select></Field><Field label="Redirect fraction"><Input type="number" min="0" max="1" step="0.1" value={fraction} onChange={(e) => setFraction(Number(e.target.value))} /></Field></>}
      <div className="grid grid-cols-2 gap-2"><Field label="Action start (s)"><Input type="number" min="0" value={start} onChange={(e) => setStart(Number(e.target.value))} /></Field><Field label="Action end (s)"><Input type="number" min="1" value={end} onChange={(e) => setEnd(Number(e.target.value))} /></Field></div>
      {type === "staggered_release" && <Field label="Release delay (s)"><Input type="number" min="0" value={delay} onChange={(e) => setDelay(Number(e.target.value))} /></Field>}
      {Object.keys(snapshot.plan.constraints.resources).map((rid) => <Field key={rid} label={`${rid} allocation`}><Input type="number" min="0" step="1" value={quantities[rid] ?? 0} onChange={(e) => setQuantities({ ...quantities, [rid]: Number(e.target.value) })} /></Field>)}
      <Field label="Depends on action IDs"><Input value={dependencies} onChange={(e) => setDependencies(e.target.value)} /></Field>
      <Field label="Action permission IDs"><Input value={permissions} onChange={(e) => setPermissions(e.target.value)} /></Field>
      <Field label={t("ui.planeditor.action_cost", { currency: snapshot.plan.constraints.currency })}><Input type="number" min="0" value={cost} onChange={(e) => setCost(e.target.value)} /></Field>
    </fieldset>
    <Button disabled={!id.trim() || test.isPending} onClick={propose}>{t("ui.planeditor.preview_action")}</Button>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {preview && <div role="status" className="space-y-2 rounded border border-border p-3">
      <strong>{preview.result.valid ? t("ui.planeditor.valid_proposal_not_saved") : t("ui.planeditor.proposal_rejected_nothing_saved")}</strong>
      {preview.result.issues.map((i, n) => <p key={n} className="text-sm text-danger">{i.message} ({i.code})</p>)}
      {preview.result.candidate?.plan.actions.map((a) => <ActionDetails key={a.action_id} action={a} />)}
      {preview.result.valid && <Button variant="primary" disabled={apply.isPending} onClick={() => apply.mutate(preview.body)}>{t("ui.planeditor.apply_operational_proposal")}</Button>}
    </div>}
  </section>;
}

export function ActionDetails({ action }: { action: PlanAction }) {
  return <div className="space-y-1 text-sm"><p className="font-medium">{action.label || action.action_id}</p><p>{action.action_id} · {action.event?.type ?? t("ui.planeditor.checklist_only")} · {action.start_s}–{action.end_s} s</p>
    <p>{t("ui.planeditor.resources_line", { list: action.resources.map((r) => `${r.quantity} ${r.resource_id}`).join(", ") || t("ui.planeditor.none_allocated") })}</p>
    {action.depends_on.length > 0 && <p>{t("ui.planeditor.after_line", { list: action.depends_on.join(", ") })}</p>}
    {action.required_approvals.length > 0 && <p>{t("ui.planeditor.permissions_line", { list: action.required_approvals.join(", ") })}</p>}
    {action.estimated_cost != null && <p>{t("ui.planeditor.cost_line", { cost: action.estimated_cost })}</p>}
  </div>;
}
