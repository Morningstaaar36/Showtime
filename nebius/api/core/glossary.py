"""Glossary shown in Help and linked from jargon in the UI."""

from __future__ import annotations

GLOSSARY: list[dict[str, str]] = [
    {
        "term": "People per m²",
        "definition": "Crowd density: how many people stand on one "
        "square metre. Around 2 is a packed standing crowd that can still move; 3.5 and above is "
        "our warning level; at 5 and above people can no longer move freely and crush risk rises.",
    },
    {
        "term": "Evacuation time (95%)",
        "definition": "Seconds from the start of evacuation "
        "until 95% of people are out (also called RSET, required safe egress time). It does not "
        "include the pre-movement time people need to react.",
    },
    {
        "term": "Peak density",
        "definition": "The highest density anywhere in the venue during "
        "the run, measured on a 1 m grid smoothed over about 2–3 m².",
    },
    {
        "term": "Latest safe time to start evacuating",
        "definition": "T_latest = T_hazard − "
        "(pre-movement time + evacuation time × safety factor). Start before this time so "
        "everyone is out, with a margin, before the hazard arrives.",
    },
    {
        "term": "Instant estimate",
        "definition": "Tier 1: a flow calculation from exit widths, "
        "walking distances and headcounts. Takes milliseconds; good for comparing options.",
    },
    {
        "term": "Full simulation",
        "definition": "Tier 3: every person is simulated with JuPedSim in an isolated "
        "sandbox. Takes seconds to minutes. A plan counts as confirmed only when its full "
        "simulations ran to the end.",
    },
    {
        "term": "Ranking run",
        "definition": "Tier 2: the same simulation stopped after 3 minutes, "
        "used to rank many attacks and fixes quickly. Results are marked partial.",
    },
    {
        "term": "Red team",
        "definition": "AI agents that design realistic failure scenarios "
        "grounded in real crowd incidents (each card cites its source).",
    },
    {
        "term": "Fix",
        "definition": "A change proposed by the blue team: a layout edit (add an "
        "exit, move a barrier) or an operational measure (staggered release, marshals). Every "
        "fix is re-simulated and kept only if it measurably helps.",
    },
    {"term": "Blocked exit", "definition": "An exit that cannot be used, from a given time."},
    {
        "term": "Stress test",
        "definition": "A full simulation of the current plan with no "
        "attack: everyone leaves through the exits chosen by the instant estimate.",
    },
    {
        "term": "Pre-movement time",
        "definition": "Time between the alarm and people starting "
        "to move (default 60 s; set it in Settings).",
    },
    {
        "term": "Safety factor",
        "definition": "Multiplier on the evacuation time in the "
        "countdown, to cover uncertainty (default 1.5).",
    },
    {
        "term": "Wind limit",
        "definition": "Screening estimate of the gust speed at which the "
        "stage roof's ballast stops holding it (uplift, sliding or overturning).",
    },
    {
        "term": "Hotspot",
        "definition": "An area where density rose above the warning level "
        "(3.5 people per m²) or the danger level (5).",
    },
    {
        "term": "Counterflow",
        "definition": "People moving against the main flow, for example "
        "entering through an exit while others leave. A key factor in crowd crushes.",
    },
    {
        "term": "Planning aid",
        "definition": "Showtime supports decisions; it is not a safety "
        "certification. Licensed engineers and authorities still sign off.",
    },
]
