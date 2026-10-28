"""Handover checklist: the selected plan in plain English, ready to print.

The selected plan is the project's current version (what the organizer accepted), not the
session's proposal. Core puts it in `extras["handover"]`, with how the session's evidence
relates to it, and each kept fix's own test in `extras["fix_evidence"]`. Every number keeps
the label of what it is based on; nothing here says "confirmed" unless the evaluation does.
"""

from __future__ import annotations

import html
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from api.core.extensions import Registry, ReportBundle
from api.core.extensions.geometry import display_names
from api.models import Fix, Venue
from api.models.plan import PlanAction, PlanData
from api.models.scene import SceneMetadata


class Config(BaseModel):
    """Checklist settings (the [config] table of plugin.toml)."""

    title: str = "Handover checklist"
    show_map: bool = True


HUMAN_APPROVAL = "Human approval records the chosen plan; it does not certify safety."
NOT_TOGETHER = (
    "These changes were tested one by one, not together: test again before relying on them."
)
EVALUATION = {
    "confirmed": "Confirmed by full simulations",
    "partially_confirmed": "Partly confirmed: the simulations stopped before everyone was out",
    "unconfirmed": "Not confirmed",
    "failed": "Confirmation failed: the simulations didn't finish",
}
PROVENANCE = {
    "measured": "Measured",
    "organizer_confirmed": "Checked by organizer",
    "imported": "Imported",
    "assumed": "Assumed",
    "unknown": "Not stated",
}
SOURCE = {"user": "Organizer", "agent": "AI", "rules": "Standard rule", "imported": "Imported"}
STAFF_EVENTS = {"marshal_redirect", "one_way", "staggered_release"}

Name = Callable[[Any], str]


def e(s: object) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def dur(s: float | None) -> str:
    if s is None:
        return "–"
    s = round(s)
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def clock(s: float | None) -> str:
    if s is None:
        return "–"
    s = round(s)
    return f"{s // 60}:{s % 60:02d}"


def num(v: float | None, d: int = 1) -> str:
    return "–" if v is None else f"{v:,.{d}f}"


def basis_label(basis: str | None, tier: int | None = None) -> str:
    """Organizer words for a result basis (the same words as the app)."""
    if basis == "completed_simulation":
        return "Quick simulation (ran to the end)" if tier == 2 else "Full simulation"
    if basis == "partial_simulation":
        return (
            "Full simulation, stopped before everyone was out"
            if tier == 3
            else "Quick simulation (first minutes only)"
        )
    if basis == "instant_estimate":
        return "Instant estimate"
    if basis == "preview":
        return "Preview (no simulator)"
    return "Unknown: the simulation didn't finish"


def side_label(side: dict[str, Any] | None) -> str:
    """What one side of a comparison is based on, with its run."""
    if not side:
        return "Not recorded"
    if side.get("fallback_for"):
        label = "Instant estimate (the simulation didn't finish)"
    else:
        label = basis_label(side.get("basis"), side.get("tier"))
    return f"{label}, run {side['run_id']}" if side.get("run_id") else label


def evac(m: dict[str, Any] | None) -> str:
    """Evacuation time (95%), or the estimate a time-capped run extrapolated."""
    if not m:
        return "–"
    if m.get("evac_time_p95_s") is not None:
        return dur(m["evac_time_p95_s"])
    if m.get("evac_time_estimate_s") is not None:
        return f"about {dur(m['evac_time_estimate_s'])} (estimated)"
    return "not reached"


def inside(m: dict[str, Any] | None) -> str:
    if not m or m.get("agents_not_evacuated") is None:
        return "–"
    return f"{int(m['agents_not_evacuated']):,}"


def describe_event(ev: dict[str, Any], name: Name) -> str:
    """A scenario measure as a steward would read it."""
    at = float(ev.get("at_s") or 0)
    when = f" from {clock(at)}" if at else ""
    kind = ev.get("type")
    if kind == "marshal_redirect":
        share = round(float(ev.get("fraction") or 0.5) * 100)
        src = f" from {name(ev['from_exit_id'])}" if ev.get("from_exit_id") else ""
        return f"Stewards send {share}% of people{src} to {name(ev.get('to_exit_id'))}{when}"
    if kind == "one_way":
        return f"One-way flow out through {name(ev.get('exit_id'))}: nobody comes back in{when}"
    if kind == "staggered_release":
        return (
            f"Hold {name(ev.get('zone_id'))} for {round(float(ev.get('delay_s') or 0))} s, "
            f"then release it{when}"
        )
    if kind == "block_exit":
        return f"{name(ev.get('exit_id'))} closed{when}"
    if kind == "unblock_exit":
        return f"{name(ev.get('exit_id'))} opened{when}"
    return str(kind).replace("_", " ")


def describe_op(op: dict[str, Any], name: Name) -> str:
    """A layout change in plain words."""
    kind = op.get("op")
    if kind == "add_exit":
        wall = f" on the {op['wall']} wall" if op.get("wall") else ""
        return f"New {op.get('width_m')} m exit{wall} ({name(op.get('id'))})"
    if kind == "resize":
        return f"Make {name(op.get('target'))} {op.get('width_m')} m wide"
    if kind == "block_exit":
        verb = "Open" if op.get("blocked") is False else "Close"
        return f"{verb} {name(op.get('exit_id'))}"
    if kind == "remove_obstacle":
        return f"Remove {name(op.get('obstacle_id'))}"
    if kind in ("add_obstacle", "add_barrier_line"):
        return f"New barrier ({name(op.get('id'))})"
    if kind == "move":
        return f"Move {name(op.get('target'))}"
    if kind == "set_people":
        return f"{name(op.get('zone_id'))}: {op.get('people')} people"
    return str(kind).replace("_", " ")


def describe_action(a: PlanAction, name: Name) -> str:
    """A staffed action with its time window and the people and equipment it needs."""
    what = describe_event(a.event.model_dump(), name) if a.event else "Checklist item"
    staff = ", ".join(f"{r.quantity} × {r.resource_id}" for r in a.resources) or "no staff"
    label = f"{a.label}: " if a.label else ""
    return f"{label}{what} ({clock(a.start_s)}–{clock(a.end_s)}, {staff})"


def describe_fix(fx: Fix, name: Name) -> list[str]:
    """Everything one fix changes: layout, measures and staffed actions."""
    return [
        *(describe_op(o.model_dump(), name) for o in fx.patch.ops),
        *(describe_event(ev.model_dump(), name) for ev in fx.operational),
        *(describe_action(a, name) for a in [*fx.actions, *fx.replace_actions]),
        *(f"Stop the saved action {aid}" for aid in fx.remove_action_ids),
    ]


def _plan(venue: Venue) -> PlanData:
    try:
        return PlanData.model_validate(venue.extensions.get("organizer_plan", {}))
    except ValueError:
        return PlanData()


def _annotations(venue: Venue) -> dict[str, Any]:
    block = venue.extensions.get("plan_annotations")
    objects = block.get("objects") if isinstance(block, dict) else None
    return objects if isinstance(objects, dict) else {}


def _metadata(venue: Venue) -> SceneMetadata:
    try:
        return SceneMetadata.model_validate(venue.extensions.get("scene_metadata", {}))
    except ValueError:
        return SceneMetadata()


def _proposed(venue: Venue, data: PlanData, oid: str) -> bool:
    entry = _annotations(venue).get(oid)
    policy = data.constraints.objects.get(oid)
    return (isinstance(entry, dict) and entry.get("change") == "proposed") or (
        policy is not None and policy.origin == "proposed"
    )


def _width_source(meta: SceneMetadata, oid: str) -> tuple[str, str]:
    p = (meta.fields.get(oid) or {}).get("width_m") or meta.objects.get(oid)
    basis = p.basis if p else "unknown"
    label = PROVENANCE.get(basis, "Not stated")
    if p is not None and p.source and basis != "unknown":
        label += f" ({p.source})"
    return label, basis


def _box() -> str:
    return '<span class="box" aria-hidden="true"></span>'


# ----------------------------------------------------------------------------- sections


def _conditions(
    b: ReportBundle,
    h: dict[str, Any],
    selected: Venue,
    data: PlanData,
    in_plan: list[Fix],
    suggested: list[Fix],
    name: Name,
) -> tuple[str, list[str]]:
    """What the tests show (one line) and the open conditions (each one to tick off)."""
    state = h.get("state", "untested")
    version = h.get("version", b.venue_version)
    ev = b.extras.get("evaluation")
    open_: list[str] = []
    if state == "untested":
        open_.append(
            "This plan has not been tested by the AI red team yet. Run a test before relying on it."
        )
    elif state == "pending":
        n = len(suggested)
        open_.append(
            f"The AI suggested {n} change{'s' if n != 1 else ''} that "
            f"{'are' if n != 1 else 'is'} not part of this plan yet. Accept them on Your plan, "
            "or hand over this plan without them."
        )
    elif state == "accepted_subset":
        kept = len(b.accepted_fix_ids)
        open_.append(
            f"This plan has {len(in_plan)} of the {kept} changes the AI kept. {NOT_TOGETHER}"
        )
    elif state == "stale":
        open_.append(
            f"This plan (version {version}) changed after the last test of version "
            f"{h.get('tested_version')}. The numbers below describe the tested version: "
            "test again before relying on them."
        )
    if isinstance(ev, dict) and ev.get("status") in EVALUATION:
        reasons = " ".join(str(r) for r in ev.get("reasons") or [])
        shows = f"Evaluation: {EVALUATION[ev['status']]}." + (f" {reasons}" if reasons else "")
        if ev["status"] != "confirmed":
            open_.append(
                "The tests do not confirm this plan yet. Read the evaluation above and test "
                "again with full simulations before relying on the numbers."
            )
        fallbacks = ev.get("fallback_run_ids") or {}
        if fallbacks:
            sides = ", ".join(sorted(fallbacks))
            open_.append(
                f"Some simulations did not finish ({sides}); instant estimates are shown in their "
                "place. Treat those numbers as unknown."
            )
        if "preview" in (ev.get("before_basis"), ev.get("after_basis")):
            open_.append("These results are previews from the mock sandbox, not simulations.")
    elif b.session_id:
        shows = "Evaluation: Not confirmed. This test was saved before evaluations were recorded."
    else:
        shows = "Evaluation: Not confirmed. No red-team test has been run."
    for aid, approval in sorted(data.constraints.approvals.items()):
        if approval.status != "approved":
            src = f" (source: {approval.source})" if approval.source else ""
            open_.append(
                f"Permission “{aid}” is {approval.status}{src}. Get it approved or drop it."
            )
    for f in selected.floors:
        for item in [*f.exits, *f.obstacles]:
            if _proposed(selected, data, item.id):
                open_.append(
                    f"Proposed construction: {name(item.id)} must be built and approved "
                    "before the event."
                )
    for a in data.actions:
        if a.event and a.event.type in STAFF_EVENTS and not a.resources:
            what = a.label or describe_event(a.event.model_dump(), name)
            open_.append(f"No staff assigned to “{what}”: assign stewards before the event.")
    meta = _metadata(selected)
    unmeasured = [
        name(x.id)
        for f in selected.floors
        for x in f.exits
        if _width_source(meta, x.id)[1] not in ("measured", "organizer_confirmed")
        and not _proposed(selected, data, x.id)
    ]
    if unmeasured:
        open_.append(
            "Exit widths nobody has measured or checked: " + ", ".join(unmeasured) + ". Measure "
            "them on site and update the plan if they differ."
        )
    return shows, open_


def _numbers(b: ReportBundle, h: dict[str, Any]) -> str:
    """Key numbers under the worst case found, each with what it is based on."""
    ev = b.extras.get("evaluation") if isinstance(b.extras.get("evaluation"), dict) else {}
    results = b.results
    state = h.get("state", "untested")

    def side(which: str) -> dict[str, Any] | None:
        metrics = b.before if which == "before" else b.after
        if not metrics:
            return None
        fb = (ev.get("fallback_run_ids") or {}).get(which)
        rid = fb or ev.get(f"{which}_run_id")
        run = results.get(str(rid)) if rid else None
        return {
            "run_id": rid,
            "basis": run.basis if run else ev.get(f"{which}_basis"),
            "tier": run.tier if run else None,
            "fallback_for": ev.get(f"{which}_run_id") if fb else None,
            "metrics": metrics,
        }

    worst = next((a for a in b.attacks if a.attack_id == b.worst_attack_id), None)
    rows = [
        ("Evacuation time (95%)", evac),
        ("People still inside at the end", inside),
        (
            "Peak density (people per m²)",
            lambda m: num(m.get("peak_density_ppm2")) if m else "–",
        ),
        ("Time above danger", lambda m: dur(m.get("time_above_danger_s")) if m else "–"),
    ]
    out = []
    before, after = side("before"), side("after")
    if before is not None:
        if after is not None:
            cols = [("Without the changes", before), ("With all the changes the AI kept", after)]
            current = {"pending": 0, "accepted": 1}.get(state)
        else:
            cols = [("Result", before)]
            current = 0 if state == "tested" else None
        head = "".join(
            f"<th>{e(t)}{' (this plan)' if i == current else ''}</th>"
            for i, (t, _) in enumerate(cols)
        )
        body = "<tr><td>Based on</td>" + "".join(
            f"<td class='muted'>{e(side_label(s))}</td>" for _, s in cols
        )
        body += "</tr>" + "".join(
            f"<tr><td>{e(label)}</td>"
            + "".join(f"<td>{e(fmt(s['metrics']))}</td>" for _, s in cols)
            + "</tr>"
            for label, fmt in rows
        )
        under = f"<p>Under the worst case found: “{e(worst.title)}”.</p>" if worst else ""
        out.append(f"{under}<table><tr><th></th>{head}</tr>{body}</table>")
        if state == "accepted_subset":
            out.append(
                "<p class='muted'>This plan has only some of these changes, so neither column "
                "describes it exactly.</p>"
            )
    base = b.baseline
    if base is not None:
        m = base.metrics
        bl = (
            "Instant estimate (the simulation didn't finish)"
            if base.extensions.get("fallback_for")
            else basis_label(base.basis, base.tier)
        )
        p95 = dur(m.evac_time_p95_s) if m.evac_time_p95_s is not None else "not reached"
        out.append(
            "<p>Normal evacuation (no incident): evacuation time (95%) "
            f"<b>{e(p95)}</b>, {m.agents_not_evacuated:,} people still inside at the end, "
            f"peak density {num(m.peak_density_ppm2)} people per m². "
            f"<span class='muted'>{e(bl)}, run {e(base.run_id)}</span></p>"
        )
    cd = b.countdown
    if cd is not None:
        if cd.status == "ok":
            head_cd = (
                f"start evacuating by {cd.t_latest_iso[11:16]}"
                if cd.t_latest_iso
                else f"start within {dur(cd.t_latest_s)} of the alarm"
            )
        elif cd.status == "too_late":
            head_cd = "too late to evacuate safely before the hazard"
        elif cd.status == "no_hazard":
            head_cd = "no hazard in the forecast window"
        else:
            head_cd = "not known"
        source = f" From: {cd.rset_source}." if cd.rset_source else ""
        out.append(
            f"<p>Latest safe time to start evacuating: <b>{e(head_cd)}</b>."
            f"<span class='muted'>{e(source)}</span></p>"
        )
    if not out:
        return "<p class='muted'>No simulation results for this plan yet.</p>"
    out.append(
        "<p class='muted'>The evacuation time (95%) is the time for 95% of people to get out, "
        "not everyone; people still inside are listed next to it.</p>"
    )
    return "".join(out)


def _gates(selected: Venue, tested: Venue, data: PlanData, name: Name) -> str:
    """Every gate and door of the selected plan, against the tested venue."""
    meta = _metadata(selected)
    before = {x.id: x for f in tested.floors for x in f.exits}
    rows = ""
    now: set[str] = set()
    for f in selected.floors:
        floor = f.name or f.floor_id
        for x in f.exits:
            now.add(x.id)
            old = before.get(x.id)
            if old is None:
                change = "New"
            elif old.width_m != x.width_m:
                verb = "Widened" if x.width_m > old.width_m else "Narrowed"
                change = f"{verb} from {num(old.width_m)} m"
            elif old.blocked != x.blocked:
                change = "Closed in this plan" if x.blocked else "Opened in this plan"
            else:
                change = "No change"
            state = "Closed" if x.blocked else "Open"
            policy = data.constraints.objects.get(x.id)
            if policy is not None and policy.access == "unavailable":
                state += " · access unavailable"
            elif policy is not None and policy.access == "restricted":
                needs = ", ".join(policy.required_approvals) or "a permission"
                state += f" · restricted (needs {needs})"
            origin = "Proposed" if _proposed(selected, data, x.id) else "Existing"
            rows += (
                f"<tr><td>{_box()}</td><td><b>{e(name(x.id))}</b></td><td>{e(floor)}</td>"
                f"<td class='num'>{num(x.width_m)} m</td><td>{e(state)}</td><td>{origin}</td>"
                f"<td>{e(change)}</td><td class='muted'>{e(_width_source(meta, x.id)[0])}</td></tr>"
            )
    for oid, x in before.items():
        if oid not in now:
            rows += (
                f"<tr><td>{_box()}</td><td><b>{e(name(oid))}</b></td><td>–</td>"
                f"<td class='num'>{num(x.width_m)} m</td><td>Removed</td><td>Existing</td>"
                "<td>Removed in this plan</td><td></td></tr>"
            )
    if not rows:
        return "<p class='muted'>This venue has no exits.</p>"
    return (
        "<table><tr><th class='tick'></th><th>Gate or door</th><th>Floor</th><th>Width</th>"
        "<th>Open or closed</th><th>Existing or proposed</th><th>In this plan</th>"
        f"<th>Width source</th></tr>{rows}</table>"
    )


def _actions(data: PlanData, name: Name) -> str:
    """Staff and equipment actions saved in the plan, in time order."""
    if not data.actions:
        return "<p class='muted'>No staff or equipment actions are saved in this plan.</p>"
    labels = {a.action_id: a.label or a.action_id for a in data.actions}
    pools = data.constraints.resources

    def staff(a: PlanAction) -> str:
        if not a.resources:
            return "None assigned"
        return ", ".join(
            f"{r.quantity} × {r.resource_id}"
            + (f" ({pools[r.resource_id].kind})" if r.resource_id in pools else "")
            for r in a.resources
        )

    def approvals(a: PlanAction) -> str:
        found = data.constraints.approvals
        return ", ".join(
            f"{aid} ({found[aid].status if aid in found else 'unknown'})"
            for aid in a.required_approvals
        )

    rows = ""
    for a in sorted(data.actions, key=lambda x: (x.start_s, x.action_id)):
        what = describe_event(a.event.model_dump(), name) if a.event else "Checklist item"
        title = f"<b>{e(a.label)}</b><br>" if a.label else ""
        rows += (
            f"<tr><td>{_box()}</td><td class='num'>{clock(a.start_s)}–{clock(a.end_s)}</td>"
            f"<td>{title}{e(what)}</td><td>{e(staff(a))}</td>"
            f"<td>{e(', '.join(labels.get(d, d) for d in a.depends_on) or '–')}</td>"
            f"<td>{e(approvals(a) or '–')}</td><td>{e(SOURCE.get(a.source, a.source))}</td></tr>"
        )
    resources = "".join(
        f"<tr><td>{e(rid)}</td><td>{e(p.kind)}</td><td class='num'>{p.count:,}</td>"
        f"<td class='num'>{clock(p.available_from_s)}–{clock(p.available_until_s)}</td></tr>"
        for rid, p in sorted(pools.items())
    )
    return (
        "<table><tr><th class='tick'></th><th>When</th><th>What to do</th>"
        "<th>Staff and equipment</th><th>After</th><th>Permissions</th><th>Source</th></tr>"
        f"{rows}</table><p class='muted'>Times are minutes:seconds after the evacuation starts.</p>"
        + (
            "<h3>Staff and equipment available</h3><table><tr><th>Resource</th><th>Kind</th>"
            f"<th>Count</th><th>Available</th></tr>{resources}</table>"
            if resources
            else ""
        )
    )


def _fixes(
    fixes: list[Fix], evidence: dict[str, Any], b: ReportBundle, name: Name, accepted: bool
) -> str:
    """Each change with what it does, where it came from and its own test."""
    titles = {a.attack_id: a.title for a in b.attacks}
    items = ""
    for fx in fixes:
        what = "; ".join(describe_fix(fx, name)) or "No layout change"
        source = "Standard rule" if fx.extensions.get("generated_by") == "rules" else "AI"
        test = evidence.get(fx.fix_id) or {}
        before, after = test.get("before"), test.get("after")
        tested = ""
        if before and after:
            bm, am = before.get("metrics") or {}, after.get("metrics") or {}
            under = titles.get(str(test.get("attack_id")), "its scenario")
            labels = {side_label(before).split(", run")[0], side_label(after).split(", run")[0]}
            tested = (
                f"<br><span class='muted'>Tested on its own under “{e(under)}”: evacuation time "
                f"(95%) {e(evac(bm))} → {e(evac(am))}; peak density "
                f"{num(bm.get('peak_density_ppm2'))} → {num(am.get('peak_density_ppm2'))} people "
                f"per m²; time above danger {dur(bm.get('time_above_danger_s'))} → "
                f"{dur(am.get('time_above_danger_s'))}. Based on: {e(' / '.join(sorted(labels)))} "
                f"(runs {e(before.get('run_id'))} → {e(after.get('run_id'))}).</span>"
            )
        items += (
            f"<li>{_box() if accepted else ''}<b>{e(fx.title)}</b> <span class='tag'>{source}</span>"
            f"<br>{e(what)}{tested}</li>"
        )
    return f"<ul class='fixes'>{items}</ul>"


CSS = """
:root{--plan:#F6F7FF;--ink:#1D1B3A;--muted:#55607A;--border:#D7DBEE;--signal:#5B4FF5;
--egress:#0F7A46;--caution:#9A5B00;--danger:#C62838}
*{box-sizing:border-box}
body{margin:0;background:var(--plan);color:var(--ink);font:14px/1.5 "Public Sans",Helvetica,Arial,
sans-serif;font-variant-numeric:tabular-nums}
main{max-width:900px;margin:24px auto;background:#fff;padding:36px 44px;border:1px solid var(--border)}
h1{font-size:26px;margin:4px 0 2px}h2{font-size:18px;margin:28px 0 8px;padding-top:12px;
border-top:1px solid var(--border)}h3{font-size:14px;margin:14px 0 6px}
.eyebrow{color:var(--signal);font-weight:600;font-size:12px}.muted{color:var(--muted)}
.disclaimer{margin:14px 0;padding:8px 12px;border-left:4px solid var(--danger);background:#FDECEE;
font-weight:600}
.shows{padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:#F3F5FC}
.shows.ok{background:#E2F5EA}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}
th{text-align:left;color:var(--muted);font-weight:600;border-bottom:1.5px solid var(--ink);padding:5px 6px}
td{border-bottom:1px solid var(--border);padding:5px 6px;vertical-align:top}
td.num{white-space:nowrap}th.tick{width:22px}
.box{display:inline-block;width:13px;height:13px;border:1.5px solid var(--ink);border-radius:2px;
margin-right:8px;vertical-align:-2px}
ul.open,ul.fixes{list-style:none;padding-left:0}ul.open li,ul.fixes li{margin:6px 0}
.tag{display:inline-block;padding:0 6px;border-radius:3px;font-size:11px;font-weight:600;
background:#ECEBFF;color:var(--signal)}
.map{margin-top:10px;border:1px solid var(--border);border-radius:8px;overflow:hidden}
.map svg{width:100%;height:auto;display:block}
.sign{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:12px}
.sign div{border-bottom:1px solid var(--ink);padding-top:28px;font-size:12px;color:var(--muted)}
footer{margin-top:28px;font-size:11px;color:var(--muted)}
.toolbar{max-width:900px;margin:16px auto 0;display:flex;justify-content:flex-end}
.toolbar button{font:inherit;border:1px solid var(--border);background:#fff;border-radius:6px;
padding:6px 12px;cursor:pointer}
@media print{body{background:#fff}main{margin:0;border:0;padding:0}.toolbar{display:none}
h2{break-after:avoid}table,.map,li{break-inside:avoid}@page{size:A4;margin:14mm 12mm 16mm;
@bottom-left{content:"Planning aid, not a safety certification.";font-size:9px;color:#C62838}
@bottom-right{content:counter(page) " / " counter(pages);font-size:9px}}}
"""


def render(b: ReportBundle, cfg: Config | None = None) -> str:
    """The checklist as a complete, printable HTML document."""
    cfg = cfg or Config()
    h = b.extras.get("handover") if isinstance(b.extras.get("handover"), dict) else {}
    selected = Venue.model_validate(h["venue"]) if h.get("venue") else b.venue
    version = h.get("version", b.venue_version)
    state = h.get("state", "untested" if not b.session_id else "tested")
    labels = display_names(selected, b.venue, b.fixed_venue)
    for f in b.venue.floors:  # an unnamed existing exit keeps its id; only added ones are "new"
        labels.update({x.id: x.id for x in f.exits if not x.label})

    def name(x: Any) -> str:
        return labels.get(str(x), str(x))

    data = _plan(selected)
    by_id = {f.fix_id: f for f in b.fixes}
    in_plan = [by_id[f] for f in h.get("fix_ids") or [] if f in by_id]
    suggested = [by_id[f] for f in h.get("suggested_fix_ids") or [] if f in by_id]
    evidence = b.extras.get("fix_evidence") or {}
    shows, open_ = _conditions(b, h, selected, data, in_plan, suggested, name)
    ev = b.extras.get("evaluation")
    confirmed = isinstance(ev, dict) and ev.get("status") == "confirmed"
    conditions = (
        "<ul class='open'>" + "".join(f"<li>{_box()}{e(c)}</li>" for c in open_) + "</ul>"
        if open_
        else "<p class='muted'>No open conditions were found.</p>"
    )
    if in_plan:
        changes = "<h2>Changes in this plan</h2>" + _fixes(in_plan, evidence, b, name, True)
        if state == "accepted_subset":
            changes += f"<p class='muted'>{e(NOT_TOGETHER)}</p>"
    elif suggested:
        changes = (
            "<h2>Changes the AI suggested (not accepted yet)</h2>"
            "<p class='muted'>They are not part of this plan. Accept them on Your plan to "
            "include them.</p>" + _fixes(suggested, evidence, b, name, False)
        )
    else:
        changes = ""
    map_svg = b.extras.get("map_svg") if cfg.show_map else ""
    assumptions = "".join(
        f"<tr><td>{e(a.get('name'))}</td><td>{e(a.get('value'))}</td>"
        f"<td class='muted'>{e(a.get('source'))}</td></tr>"
        for a in b.assumptions
    )
    digest = str(h.get("plan_hash") or "")
    identity = f" · plan identity {e(digest[:19])}" if digest else ""
    people = selected.total_people()
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(cfg.title)} · {e(b.project_name)}</title><style>{CSS}</style></head><body>
<div class="toolbar"><button onclick="window.print()">Print or save as PDF</button></div>
<main>
<div class="eyebrow">Showtime · {e(cfg.title.lower())}</div>
<h1>{e(b.project_name)}</h1>
<div class="muted">{e(selected.name)} · version {version} (the selected plan) · {people:,} people ·
generated {e(b.generated_at)}{identity}</div>
<div class="disclaimer">{e(b.disclaimer)} {e(HUMAN_APPROVAL)}</div>
<h2>Before you sign off</h2>
<p class="shows{" ok" if confirmed else ""}">{e(shows)}</p>
{conditions}
<h2>Key numbers</h2>
{_numbers(b, h)}
<h2>Gates and doors</h2>
{_gates(selected, b.venue, data, name)}
<h2>Staff and equipment actions</h2>
{_actions(data, name)}
{changes}
{f'<h2>Map of this plan</h2><div class="map">{map_svg}</div>' if map_svg else ""}
<h2>Assumptions</h2>
<table><tr><th>Item</th><th>Value</th><th>Source</th></tr>{assumptions}</table>
<h2>Sign-off</h2>
<p>{e(HUMAN_APPROVAL)}</p>
<div class="sign"><div>Name and role</div><div>Date and time</div></div>
<footer>{e(b.disclaimer)} Handover checklist generated by Showtime 0.1 for version {version}.</footer>
</main></body></html>"""


class ChecklistExporter:
    """Exporter: printable handover checklist of the selected plan."""

    id = "export_checklist"
    label = "Handover checklist (HTML)"
    media_type = "text/html"
    file_ext = "html"

    def __init__(self, config: Config) -> None:
        self.config = config

    def render(self, bundle: ReportBundle) -> bytes:
        return render(bundle, self.config).encode()


def showtime_register(registry: Registry, config: Config) -> None:
    """Register the exporter."""
    registry.add("Exporter", ChecklistExporter.id, ChecklistExporter(config))
