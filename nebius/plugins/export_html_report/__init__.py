"""Printable report (HTML; print to PDF from the browser). Self-contained: inline CSS and SVG."""

from __future__ import annotations

import html
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from api.core.extensions import Registry, ReportBundle
from api.core.extensions.breaks import BreakRule, at_risk, break_reasons
from api.core.extensions.geometry import display_names
from api.models import RunResult


class Config(BaseModel):
    """No settings."""


def e(s: object) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def dur(s: float | None) -> str:
    if s is None:
        return "–"
    s = round(s)
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def num(v: float | None, d: int = 1) -> str:
    return "–" if v is None else f"{v:,.{d}f}"


def clock(s: float | None) -> str:
    if s is None:
        return "–"
    s = round(s)
    return f"{s // 60}:{s % 60:02d}"


def _same(x: Any) -> str:
    return str(x)


def describe_event(ev: dict[str, Any], name: Callable[[Any], str] = _same) -> str:
    t = ev.get("at_s") or 0
    at = f" at {clock(t)}" if t else ""
    k = ev.get("type")
    if k == "block_exit":
        return f"{name(ev.get('exit_id'))} blocked{at}"
    if k == "surge":
        return f"{ev.get('extra_people')} more people into {name(ev.get('zone_id'))}{at}"
    if k == "slowdown":
        return f"walking speed × {ev.get('factor')}{at}"
    if k == "counterflow":
        return f"{ev.get('people')} people push in through {name(ev.get('exit_id'))}{at}"
    if k == "staggered_release":
        return f"hold {name(ev.get('zone_id'))} for {ev.get('delay_s')} s"
    if k == "marshal_redirect":
        return f"marshals send people to {name(ev.get('to_exit_id'))}{at}"
    if k == "one_way":
        return f"one-way flow at {name(ev.get('exit_id'))}"
    return str(k)


def describe_op(o: dict[str, Any], name: Callable[[Any], str] = _same) -> str:
    k = o.get("op")
    if k == "add_exit":
        return f"new {o.get('width_m')} m exit" + (
            f" on the {o.get('wall')} wall" if o.get("wall") else ""
        )
    if k == "resize":
        return f"widen {name(o.get('target'))} to {o.get('width_m')} m"
    if k == "add_barrier_line":
        return "new barrier line"
    if k == "move":
        return f"move {name(o.get('target'))}"
    if k == "remove_obstacle":
        return f"remove {name(o.get('obstacle_id'))}"
    return str(k)


def verdict(r: RunResult | None, rule: BreakRule | None) -> tuple[str, str]:
    """Headline verdict; it never claims more than the result's basis supports."""
    if r is None:
        return "Not tested", "neutral"
    if r.basis == "preview":
        return "Preview only — not simulated", "neutral"
    if r.basis == "unknown":
        return "Simulation did not complete", "neutral"
    if r.basis == "instant_estimate":
        return "Instant estimate only — not simulated", "neutral"
    if rule is None:  # a bundle without the server's rules: say so rather than guess
        return "Not judged", "neutral"
    if break_reasons(r, rule):
        return "Fails", "danger"
    if at_risk(r, rule):
        return "At risk", "caution"
    if r.basis == "partial_simulation":
        return "Test incomplete", "neutral"
    return "Holds", "egress"


def basis_label(basis: str | None, tier: int = 3) -> str:
    """Plain words for a result basis (see `RunResult.basis`)."""
    if basis == "completed_simulation":
        return "full simulation" if tier == 3 else "quick simulation (ran to the end)"
    if basis == "partial_simulation":
        return (
            "quick simulation (first minutes only)"
            if tier == 2
            else "full simulation, stopped before everyone was out"
        )
    if basis == "instant_estimate":
        return "instant estimate"
    if basis == "preview":
        return "preview only (no simulation)"
    return "simulation did not complete"


def source_label(run: RunResult | None) -> str:
    """What a result is based on, derived from its basis; never a confirmation claim."""
    if run is None:
        return "not tested"
    if run.extensions.get("fallback_for"):
        return "instant estimate (the simulation did not finish)"
    return basis_label(run.basis, run.tier)


def shown_result(run: RunResult | None, results: dict[str, RunResult]) -> RunResult | None:
    """The result to show for `run`: the linked instant estimate when it did not finish."""
    if run is None or run.basis != "unknown":
        return run
    return next(
        (r for r in results.values() if r.extensions.get("fallback_for") == run.run_id), run
    )


EVALUATION = {
    "confirmed": ("Confirmed by full simulations", "egress"),
    "partially_confirmed": ("Partly confirmed", "caution"),
    "unconfirmed": ("Not confirmed", "neutral"),
    "failed": ("Confirmation failed", "danger"),
}


def _evaluation_html(ev: Any) -> str:
    """Evaluation status of the plan, separate from whether the session finished."""
    if not isinstance(ev, dict) or ev.get("status") not in EVALUATION:
        return ""
    label, tone = EVALUATION[ev["status"]]
    reasons = " ".join(e(r) for r in ev.get("reasons", []))
    return f'<p class="evaluation {tone}"><b>Evaluation: {e(label)}.</b> {reasons}</p>'


def _side_label(ev: Any, side: str) -> str:
    """Basis of one side of the before/after comparison (confirmation runs are tier 3)."""
    if not isinstance(ev, dict):
        return ""
    if (ev.get("fallback_run_ids") or {}).get(side):
        return "instant estimate (the simulation did not finish)"
    return basis_label(ev.get(f"{side}_basis"), 3) if ev.get(f"{side}_basis") else ""


def _int(v: Any) -> str:
    return "–" if v is None else f"{int(v):,}"


def _cost_html(cost: Any, tokens_total: int, cost_usd: float) -> str:
    """How this plan was made: measured model and compute usage of the session."""
    if not isinstance(cost, dict):
        if not tokens_total:
            return ""
        return (
            "<h2>How this plan was made</h2>"
            f"<p>AI usage: {tokens_total:,} tokens (${cost_usd:.4f}). "
            "Simulation counts were not recorded for this session.</p>"
        )
    sims = cost.get("sims") or {}
    usd = float(cost.get("usd_total") or 0.0)
    total = f"${usd:.4f}" if usd else "$0 (free or local models)"
    models = "".join(
        f"<tr><td>{e(name)}</td><td class='num'>{_int(b.get('calls'))}</td>"
        f"<td class='num'>{_int(b.get('tokens_in'))}</td>"
        f"<td class='num'>{_int(b.get('tokens_out'))}</td>"
        f"<td class='num'>${float(b.get('usd') or 0.0):.4f}</td></tr>"
        for name, b in sorted((cost.get("by_model") or {}).items())
    )
    reused = int(sims.get("cache_hits") or 0)
    failed = int(sims.get("failed") or 0)
    notes = [f"{failed:,} did not finish" if failed else "", f"{reused:,} reused" if reused else ""]
    extra = ", ".join(n for n in notes if n)
    rows = [
        ("AI model cost", total),
        (
            "Model calls",
            f"{_int(cost.get('calls'))} ({_int(cost.get('tokens_in'))} tokens in, "
            f"{_int(cost.get('tokens_out'))} out"
            + (
                f"; {_int(cost.get('llm_cache_hits'))} answered from the cache"
                if cost.get("llm_cache_hits")
                else ""
            )
            + ")",
        ),
        ("Instant estimates", _int(sims.get("instant_estimates"))),
        ("Quick simulations", _int(sims.get("quick_sims"))),
        ("Full simulations", _int(sims.get("full_sims"))),
        ("Simulation compute time", dur(sims.get("sim_seconds"))),
        ("Wall time", dur(cost.get("wall_s"))),
    ]
    table = "".join(f"<tr><td>{e(k)}</td><td>{e(v)}</td></tr>" for k, v in rows)
    return (
        "<h2>How this plan was made</h2>"
        "<p class='muted'>Measured for this session: model calls and their cost, and every "
        "simulation by kind" + (f" ({e(extra)})" if extra else "") + ". Compute time counts "
        "fresh sandbox runs only; local hosting and electricity are not included.</p>"
        f"<table>{table}</table>"
        + (
            "<h3>Models used</h3><table><tr><th>Model</th><th>Calls</th><th>Tokens in</th>"
            f"<th>Tokens out</th><th>Cost</th></tr>{models}</table>"
            if models
            else ""
        )
    )


def _attack_result(r: RunResult | None, shown: RunResult | None, broke: bool, why: str) -> str:
    """Result cell for one attack, labelled by what the result is based on."""
    if r is None or shown is None:
        return "–"
    numbers = f"{num(shown.metrics.peak_density_ppm2)} /m² · {dur(shown.metrics.time_above_danger_s)} above danger"
    reasons = f"<br><span class=muted>{why}</span>" if why else ""
    if shown.basis == "preview":
        return e(source_label(shown))
    if shown.basis == "unknown":
        return e(source_label(r))
    if shown is not r or shown.basis == "instant_estimate":
        # an estimate shown in place of a failed simulation: labelled, never a verdict
        return (
            f"{e(source_label(r))}<br><span class=muted>{e(source_label(shown))}: {numbers}</span>"
        )
    if shown.basis == "partial_simulation" and not broke:
        return (
            f'<span class="tag neutral">no break seen</span><br>{numbers}'
            f"<br><span class=muted>{e(source_label(shown))}</span>"
        )
    return (
        f'<span class="tag {"danger" if broke else "egress"}">{"breaks" if broke else "holds"}</span>'
        f"<br>{numbers}{reasons}"
    )


CSS = """
:root{--plan:#EEF2F4;--ink:#1C2329;--muted:#55626D;--line:#8E9BA5;--border:#D3DBE1;--signal:#1F5FBF;
--egress:#0A7F4F;--caution:#B97F00;--danger:#C62828}
*{box-sizing:border-box}
body{margin:0;background:var(--plan);color:var(--ink);font:14px/1.5 "Public Sans",Helvetica,Arial,sans-serif;
font-variant-numeric:tabular-nums}
main{max-width:860px;margin:24px auto;background:#fff;padding:40px 48px;border:1px solid var(--border)}
h1{font-size:26px;margin:4px 0 2px;letter-spacing:-.01em}h2{font-size:18px;margin:32px 0 10px;
padding-top:14px;border-top:1px solid var(--border)}h3{font-size:14px;margin:16px 0 6px}
.eyebrow{color:var(--signal);font-weight:600;font-size:12px}.muted{color:var(--muted)}
.disclaimer{margin:14px 0;padding:8px 12px;border-left:4px solid var(--danger);background:#F9E0DF;font-weight:600}
.verdict{display:flex;gap:16px;align-items:center;padding:14px 16px;border-radius:10px;margin-top:18px}
.verdict.danger{background:#F9E0DF;border:1px solid #e9b4b2}.verdict.caution{background:#F8EDD2;border:1px solid #e8d29c}
.verdict.egress{background:#DDF1E8;border:1px solid #a9d7c2}.verdict.neutral{background:#F3F6F8;border:1px solid var(--border)}
.verdict b{font-size:20px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-top:12px}
.evaluation{margin-top:10px;padding:8px 12px;border-radius:8px;border:1px solid var(--border)}
.evaluation.egress{background:#DDF1E8}.evaluation.caution{background:#F8EDD2}
.evaluation.danger{background:#F9E0DF}.evaluation.neutral{background:#F3F6F8}
.tile{border:1px solid var(--border);border-radius:8px;padding:10px}.tile .v{font-size:20px;font-weight:700}
.tile .l{font-size:11px;color:var(--muted)}.tile .s{font-size:10px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}
th{text-align:left;color:var(--muted);font-weight:600;border-bottom:1.5px solid var(--ink);padding:5px 6px}
td{border-bottom:1px solid var(--border);padding:5px 6px;vertical-align:top}
.tag{display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;font-weight:600}
.tag.danger{background:#F9E0DF;color:var(--danger)}.tag.egress{background:#DDF1E8;color:var(--egress)}
.tag.neutral{background:#E7ECEF;color:var(--ink)}
.countdown{display:grid;grid-template-columns:1.3fr 1fr;gap:16px;align-items:center;border:1px solid var(--border);
border-radius:10px;padding:14px 16px}.countdown .big{font-size:26px;font-weight:700}
.map{margin-top:10px;border:1px solid var(--border);border-radius:8px;overflow:hidden}.map svg{width:100%;height:auto;display:block}
a{color:var(--signal)}ol,ul{padding-left:20px}footer{margin-top:28px;font-size:11px;color:var(--muted)}
.toolbar{max-width:860px;margin:16px auto 0;display:flex;justify-content:flex-end;gap:8px}
.toolbar button{font:inherit;border:1px solid var(--border);background:#fff;border-radius:6px;padding:6px 12px;cursor:pointer}
@media print{body{background:#fff}main{margin:0;border:0;padding:0}.toolbar{display:none}h2{break-after:avoid}
table,.countdown,.map,.verdict{break-inside:avoid}@page{size:A4;margin:16mm 14mm 18mm;
@bottom-left{content:"Planning aid, not a safety certification.";font-size:9px;color:#C62828}
@bottom-right{content:counter(page) " / " counter(pages);font-size:9px}}}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
"""


def _estimates_html(est: Any) -> str:
    """Capacity, staffing, sanitation and budget table (from planning ratios, with sources)."""
    if not est:
        return ""
    rows = "".join(
        f"<tr><td>{e(ln['label'])}</td><td class='num'>{ln['value']:,.0f} {e(ln['unit'])}</td>"
        f"<td>{e(ln['detail'])}</td><td class='muted'>{e(ln['source'])}</td></tr>"
        for ln in est.get("lines", [])
    )
    cur = e(est.get("currency", "USD"))
    budget = "".join(
        f"<tr><td>{e(b['item'])}</td><td class='num'>{b['quantity']:,.0f} {e(b['unit'])}</td>"
        f"<td class='num'>{b['unit_cost']:,.0f}</td><td class='num'>{b['total']:,.0f}</td></tr>"
        for b in est.get("budget", [])
    )
    note = (
        "Example unit prices; replace them with local quotes."
        if est.get("prices_are_examples")
        else "Unit prices entered in Settings."
    )
    return (
        "<h2>Plan for the day</h2>"
        f"<p class='muted'>{e(est.get('disclaimer', ''))}</p>"
        "<table><tr><th>Item</th><th>Estimate</th><th>Basis</th><th>Source</th></tr>"
        f"{rows}</table>"
        f"<h3>Budget ({cur})</h3><p class='muted'>{note}</p>"
        "<table><tr><th>Item</th><th>Quantity</th><th>Unit price</th><th>Total</th></tr>"
        f"{budget}<tr><td colspan='3'><b>Total</b></td>"
        f"<td class='num'><b>{est.get('budget_total', 0):,.0f}</b></td></tr></table>"
    )


def render(b: ReportBundle) -> str:
    """The report as a complete HTML document."""
    evaluation = b.extras.get("evaluation")
    run = shown_result(b.final, b.results) or b.baseline
    v_text, v_tone = verdict(run, b.break_rule)
    venue = b.fixed_venue or b.venue
    labels = display_names(b.venue, b.fixed_venue)

    def name(x: Any) -> str:
        return labels.get(str(x), str(x))

    tier = source_label(run)
    m = run.metrics if run else None
    tiles = ""
    if m and run is not None and run.basis != "unknown":
        # the 95% time is not "everyone out": people still inside sit right next to it
        tiles = "".join(
            f'<div class="tile"><div class="l">{lbl}</div><div class="v">{val}</div><div class="s">{tier}</div></div>'
            for lbl, val in [
                ("People", f"{m.agents_total:,}"),
                ("Evacuation time (95%)", dur(m.evac_time_p95_s)),
                ("Still inside at the end", f"{m.agents_not_evacuated:,}"),
                ("Peak density", f"{num(m.peak_density_ppm2)} /m²"),
                ("Time above danger", dur(m.time_above_danger_s)),
            ]
        )
    cd = b.countdown
    countdown = ""
    if cd is not None:
        if cd.status == "ok":
            head = (
                f"Start evacuating by {cd.t_latest_iso[11:16]}"
                if cd.t_latest_iso
                else f"Start within {dur(cd.t_latest_s)} of the alarm"
            )
        elif cd.status == "too_late":
            head = "Too late to evacuate safely before the hazard"
        else:
            head = "No hazard in forecast window"
        countdown = (
            f'<h2>Latest safe time to start evacuating</h2><div class="countdown"><div>'
            f'<div class="big">{e(head)}</div><p class="muted">{e(cd.hazard_explanation)}</p></div>'
            f"<table><tr><td>Hazard</td><td>{e(cd.t_hazard_iso[11:16] if cd.t_hazard_iso else '–')}</td></tr>"
            f"<tr><td>Pre-movement</td><td>{dur(cd.pre_movement_s)}</td></tr>"
            f"<tr><td>Evacuation time (95%)</td><td>{dur(cd.rset_s)}</td></tr>"
            f"<tr><td>Safety factor</td><td>× {cd.safety_factor}</td></tr></table></div>"
            f'<p class="muted" style="font-size:11px">{e(cd.formula)}'
            + (f" · Evacuation time from: {e(cd.rset_source)}" if cd.rset_source else "")
            + ". The evacuation time is the time for 95% of people to get out, not everyone.</p>"
        )
    recs = "".join(f"<li>{e(r)}</li>" for r in b.recommendations)
    scoreboard = " → ".join(f"{s['breaks']}" for s in b.scoreboard)
    results_by_attack: dict[str, RunResult] = {}
    for r in b.results.values():
        if r.attack_id and not r.fix_id and r.tier == 2:
            results_by_attack[r.attack_id] = r
    attack_rows = ""
    for a in b.attacks:
        r = results_by_attack.get(a.attack_id)
        info = b.extras.get("run_info", {}).get(r.run_id, {}) if r is not None else {}
        broke = bool(info.get("is_break"))
        why = "<br>".join(e(x) for x in info.get("break_reasons", [])[:2])
        result = _attack_result(r, shown_result(r, b.results), broke, why)
        attack_rows += (
            f"<tr><td><b>{e(a.attack_id)}</b> {e(a.title)}<br><span class='muted'>"
            f"{e('; '.join(describe_event(ev.model_dump(), name) for ev in a.events))}</span></td>"
            f"<td><a href='{e(a.inspired_by.source_url)}'>{e(a.inspired_by.incident)}</a>"
            f"{' (' + str(a.inspired_by.year) + ')' if a.inspired_by.year else ''}</td><td>{result}</td></tr>"
        )
    fix_rows = ""
    for f in b.fixes:
        kept = f.fix_id in b.accepted_fix_ids
        what = "; ".join(
            [describe_op(o.model_dump(), name) for o in f.patch.ops]
            + [describe_event(ev.model_dump(), name) for ev in f.operational]
            + [
                f"{a.label or a.action_id}: {a.start_s:g}–{a.end_s:g} s; resources "
                + ", ".join(f"{r.quantity} {r.resource_id}" for r in a.resources)
                + ("; after " + ", ".join(a.depends_on) if a.depends_on else "")
                for a in [*f.actions, *f.replace_actions]
            ]
            + ["Remove action " + aid for aid in f.remove_action_ids]
        )
        fix_rows += (
            f"<tr><td><b>{e(f.fix_id)}</b> {e(f.title)}<br><span class='muted'>{e(what)}</span></td>"
            f"<td>{e(f.for_attack)}</td><td>{e(f.cost_label)}</td>"
            f"<td><span class='tag {'egress' if kept else 'neutral'}'>{'kept' if kept else 'not kept'}</span></td></tr>"
        )
    before_after = ""
    if b.before and b.after:
        bl, al = _side_label(evaluation, "before"), _side_label(evaluation, "after")
        before_after = (
            "<h3>Worst attack, before and after the kept fixes</h3><table>"
            "<tr><th></th><th>Before</th><th>After</th></tr>"
            + (
                f"<tr><td>Based on</td><td class='muted'>{e(bl)}</td><td class='muted'>{e(al)}</td></tr>"
                if bl or al
                else ""
            )
            + "".join(
                f"<tr><td>{lbl}</td><td>{fmt(b.before.get(k))}</td><td><b>{fmt(b.after.get(k))}</b></td></tr>"
                for lbl, k, fmt in [
                    ("Evacuation time (95%)", "evac_time_p95_s", dur),
                    ("People still inside at the end", "agents_not_evacuated", _int),
                    ("Peak density (people per m²)", "peak_density_ppm2", num),
                    ("Time above danger", "time_above_danger_s", dur),
                ]
            )
            + "</table>"
        )
    before_after += _evaluation_html(evaluation)
    exit_rows = ""
    if run:
        widths = {x.id: x for f in venue.floors for x in f.exits}
        for p in run.metrics.per_exit:
            ex = widths.get(p.exit_id)
            exit_rows += (
                f"<tr><td>{e(ex.label if ex and ex.label else p.exit_id)}</td><td>{num(ex.width_m if ex else None)} m</td>"
                f"<td>{p.people:,}</td><td>{num(p.mean_flow_pps)} /s</td><td>{clock(p.last_s)}</td></tr>"
            )
    hotspot_rows = "".join(
        f"<tr><td>{e(h.floor_id)}</td><td>{e(name(h.near) if h.near else f'{h.x:.0f}, {h.y:.0f} m')}</td>"
        f"<td><span class='tag {'danger' if h.level == 'danger' else 'neutral'}'>{num(h.peak_density_ppm2)}</span></td>"
        f"<td>{clock(h.t_s)}</td></tr>"
        for h in (run.hotspots[:8] if run else [])
    )
    assumption_rows = "".join(
        f"<tr><td>{e(a['name'])}</td><td>{e(a['value'])}</td><td class='muted'>{e(a['source'])}</td></tr>"
        for a in b.assumptions
    )
    sources = "".join(
        f"<li><a href='{e(s['url'])}'>{e(s['label'])}</a></li>" for s in b.sources if s.get("url")
    )
    calib = ""
    if b.calibration.get("ratio_p95"):
        c = b.calibration
        calib = (
            f"<p class='muted'>Calibration for this template: instant estimate {dur(c.get('tier1_p95_s'))} vs "
            f"simulation {dur(c.get('tier3_p95_s'))} (ratio {c['ratio_p95']:.2f}). Instant estimates are "
            "screening values; decisions use simulation results.</p>"
        )
    val = b.extras.get("validation") or {}
    if val.get("widths"):
        calib += (
            f"<p class='muted'>Simulator check: against a published bottleneck experiment with real "
            f"people (DOI {e(str(val.get('dataset_doi', '')))}), the simulated flow was "
            f"{float(val['median_abs_error_pct']):.0f}% {e(str(val.get('direction', '')))} "
            f"(median over {int(val['widths'])} widths). See Help › How good is the simulator?</p>"
        )
    map_svg = b.extras.get("map_svg", "")
    measures = b.extras.get("measures") or []
    measures_html = (
        (
            "<h3>Operational measures in the plan</h3><ul>"
            + "".join(f"<li>{e(describe_event(mm, name))}</li>" for mm in measures)
            + "</ul>"
        )
        if measures
        else ""
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Crowd-safety report · {e(b.project_name)}</title>
<style>{CSS}</style></head><body>
<div class="toolbar"><button onclick="window.print()">Print or save as PDF</button></div>
<main>
<div class="eyebrow">Showtime · crowd-safety assessment</div>
<h1>{e(b.project_name)}</h1>
<div class="muted">{e(venue.name)} · {e(venue.mode)} · version {b.venue_version}{" with red-team fixes" if b.fixed_venue else ""} ·
{venue.total_people():,} people · generated {e(b.generated_at)} · {e(b.provider_label)}</div>
<div class="disclaimer">{e(b.disclaimer)} Licensed engineers and the authorities sign off on real plans.</div>
<div class="verdict {v_tone}"><b>{e(v_text)}</b><span>{e(b.summary_text)}</span></div>
<div class="tiles">{tiles}</div>
{countdown}
{f"<h2>Recommendations</h2><ol>{recs}</ol>" if recs else ""}
{_estimates_html(b.extras.get("estimates"))}
<h2>Evacuation map</h2>
<p class="muted">Arrows show which exit each zone should use (from the flow model), with headcounts. Circles mark density hotspots.</p>
<div class="map">{map_svg}</div>
{measures_html}
{f"<h2>Red team results</h2><p>Breaks per round: <b>{e(scoreboard)}</b>. Each attack is grounded in a real incident and was tested in an isolated sandbox; the Result column says what each result is based on.</p>" if b.attacks else ""}
{f"<table><tr><th>Attack</th><th>Inspired by</th><th>Result</th></tr>{attack_rows}</table>" if attack_rows else ""}
{f"<h3>Fixes proposed by the blue team</h3><table><tr><th>Fix</th><th>For</th><th>Cost</th><th>Outcome</th></tr>{fix_rows}</table>" if fix_rows else ""}
{before_after}
<h2>Exit use</h2>
{f"<table><tr><th>Exit</th><th>Width</th><th>People</th><th>Mean flow</th><th>Last person</th></tr>{exit_rows}</table>" if exit_rows else '<p class="muted">Run a stress test to see exit use.</p>'}
{f"<h3>Hotspots</h3><table><tr><th>Floor</th><th>Near</th><th>Peak (per m²)</th><th>Time</th></tr>{hotspot_rows}</table>" if hotspot_rows else ""}
<h2>Assumptions</h2>
<table><tr><th>Item</th><th>Value</th><th>Source</th></tr>{assumption_rows}</table>
{calib}
<h2>Sources</h2><ol>{sources}</ol>
<h2>How this was computed</h2>
<p class="muted">People are simulated individually with JuPedSim in an isolated sandbox; density is measured on a 1 m grid.
Instant estimates use a flow model (exit width × specific flow) for screening. AI agents (NVIDIA Nemotron) choose what
to test and what to change; every number in this report comes from the simulator, a formula or a cited dataset.</p>
{_cost_html(b.extras.get("cost"), b.tokens_total, b.cost_usd)}
<footer>{e(b.disclaimer)} Report generated by Showtime 0.1 · run {e(run.run_id if run else "–")}</footer>
</main></body></html>"""


class HtmlReportExporter:
    """Exporter: printable HTML report."""

    id = "export_html_report"
    label = "Printable report (PDF via print)"
    media_type = "text/html"
    file_ext = "html"

    def render(self, bundle: ReportBundle) -> bytes:
        return render(bundle).encode()


def showtime_register(registry: Registry, config: Config) -> None:
    """Register the exporter."""
    registry.add("Exporter", HtmlReportExporter.id, HtmlReportExporter())
