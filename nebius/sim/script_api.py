"""Scenario scripts: AI- or user-written code that drives a crowd disaster in the sim.

A `script` event carries Python code that defines `on_step(view, act)`. The sim calls it
every `every_s` simulated seconds from `at_s`:

- `view` (a fresh read-only copy on every call): `t`, `zones[zone_id]` -> `{people,
  density}`, `exits[exit_id]` -> `{open, people_near, density, queue}`, `people_inside`,
  `zone_ids`, `exit_ids`. `people_near` counts everyone within 3 m (plus half the door
  width) of the exit, `density` is that count over the walkable part of that circle,
  `queue` is how many people are currently heading for the exit.
- `act` is the only way to change the world: `close_exit(id)`, `open_exit(id)`,
  `redirect(from_exit, to_exit, fraction)`, `add_people(zone_id, n)`, `slow_down(factor)`,
  `note(text)`. Unknown ids become a run note; nothing here crashes the run.

The code is compiled once, after the static check in `script_check.py`, with a small set
of builtins and only `math`, `statistics` and `random` importable (as copies holding their
public functions). Each call has a wall-time and line budget, the whole script a total
budget; an exception or an exceeded budget stops the script with the run note
"scenario script stopped: <reason>" and the run carries on. These guards keep a script
from stalling the run; the sandbox (no network, non-root, memory/CPU/time caps) is the
security boundary.
"""

from __future__ import annotations

import builtins
import json
import math
import os
import random
import statistics
import sys
import time
import types
from typing import Any

import numpy as np
import shapely
from memory_cap import cap_memory
from script_check import ALLOWED_IMPORTS, check_script
from shapely.geometry import Point

FILENAME = "<scenario-script>"
# Every guard on a scenario script. The API sends them with each run (Settings: SCRIPT_* and
# SANDBOX_MEMORY_SHARE in .env); these are only the fallbacks for a request without them.
GUARD_DEFAULTS: dict[str, float] = {
    "script_call_s": 0.05,  # one on_step call
    "script_total_s": 3.0,  # all calls of one script in one run
    "script_line_budget": 200_000,  # executed lines per call (deterministic busy-loop guard)
    "script_max_range": 1_000_000,  # numbers in one range()
    "script_max_acts_step": 20,
    "script_max_acts_total": 400,
    "script_max_notes": 10,
    "script_max_added_people": 2000,
    # all of a script's slow-downs together bring people to no less than this share of their
    # speed: a scenario may slow a crowd, it may not freeze it (and make every plan look broken)
    "script_min_speed_share": 0.1,
    # heap growth allowed once untrusted code runs, as a share of the container's room left
    "sandbox_memory_share": 0.85,
}
NEAR_M = 3.0


class ScriptStopped(BaseException):
    """Raised inside the script when it runs past a budget (BaseException: not catchable
    by `except Exception`, and `try` is rejected by the pre-check anyway)."""


def _safe_range(limit: int) -> Any:
    def safe_range(*args: int) -> range:
        r = range(*args)
        if len(r) > limit:
            raise ValueError(f"range of {len(r):,} numbers is too large for a scenario script")
        return r

    return safe_range


def _public_copy(mod: types.ModuleType) -> types.SimpleNamespace:
    """A module's public functions and constants, without other modules inside it."""
    names = getattr(mod, "__all__", None) or [n for n in dir(mod) if not n.startswith("_")]
    return types.SimpleNamespace(
        **{
            n: getattr(mod, n)
            for n in names
            if hasattr(mod, n) and not isinstance(getattr(mod, n), types.ModuleType)
        }
    )


SAFE_BUILTINS: dict[str, Any] = {
    name: getattr(builtins, name)
    for name in (
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "divmod",
        "enumerate",
        "filter",
        "float",
        "frozenset",
        "int",
        "isinstance",
        "len",
        "list",
        "map",
        "max",
        "min",
        "pow",
        "reversed",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
        "ArithmeticError",
        "Exception",
        "KeyError",
        "IndexError",
        "TypeError",
        "ValueError",
        "ZeroDivisionError",
    )
}
SAFE_BUILTINS["print"] = lambda *a, **k: None  # scripts talk through act.note


def _make_import(modules: dict[str, Any]) -> Any:
    def _import(
        name: str,
        globals: Any = None,
        locals: Any = None,
        fromlist: Any = (),
        level: int = 0,
    ) -> Any:
        if level or name not in modules:
            raise ImportError(f"import of '{name}' is not allowed in scenario scripts")
        return modules[name]

    return _import


def _plain(value: Any) -> bool:
    """JSON-able script state that a checkpoint can keep."""
    if isinstance(value, bool | int | float | str) or value is None:
        return True
    if isinstance(value, list | tuple):
        return all(_plain(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _plain(v) for k, v in value.items())
    return False


class ScriptRunner:
    """One `script` event on one floor: compile once, then call on_step on schedule."""

    def __init__(self, ctx: Any, ev: dict[str, Any], restore: dict[str, Any] | None = None):
        self.ev = ev
        self.title = str(ev.get("title") or "Scenario script")[:90]
        self.every_s = max(float(ev.get("every_s", 1.0) or 1.0), ctx.frame_dt)
        self.next_t = float(ev.get("at_s", 0.0))
        self.stopped = False
        self.calls = 0
        self.spent_s = 0.0
        self.acts_total = 0
        self.acts_call = 0
        self.notes = 0
        self.added = 0
        self.speed_share = 1.0  # product of this script's slow-downs so far
        settings = ctx.settings
        g = {k: float(settings.get(k, v)) for k, v in GUARD_DEFAULTS.items()}
        self.guards = g
        self.call_budget_s = g["script_call_s"]
        self.total_budget_s = g["script_total_s"]
        self.line_budget = int(g["script_line_budget"])
        self.max_acts_step = int(g["script_max_acts_step"])
        self.max_acts_total = int(g["script_max_acts_total"])
        self.max_notes = int(g["script_max_notes"])
        self.max_added = int(g["script_max_added_people"])
        self.min_speed_share = g["script_min_speed_share"]
        self.on_step: Any = None
        self.act_s = 0.0  # time spent inside act.* (sim work, not the script's own time)
        self.near_areas: dict[str, float] = {}
        self.globals: dict[str, Any] = {}
        self.act = self._make_act(ctx)
        code = str(ev.get("code", ""))
        problems = check_script(code)
        if problems:
            self._stop(ctx, f"it failed the safety check ({problems[0]})")
            return
        rnd = random.Random(int(getattr(ctx, "seed", 42)))
        rmod = _public_copy(random)
        # module-level functions of `random` would share the sim process's generator;
        # scripts get one seeded from the run seed so the same seed gives the same run
        for name in dir(rnd):
            if not name.startswith("_") and callable(getattr(rnd, name)):
                setattr(rmod, name, getattr(rnd, name))
        modules = {"math": _public_copy(math), "statistics": _public_copy(statistics)}
        modules["random"] = rmod
        assert set(modules) == set(ALLOWED_IMPORTS)
        builtins = dict(SAFE_BUILTINS)
        builtins["range"] = _safe_range(int(g["script_max_range"]))
        builtins["__import__"] = _make_import(modules)
        self.globals = {"__builtins__": builtins, "__name__": "scenario_script"}
        if os.environ.get("SHOWTIME_SANDBOX") == "1":  # set by the sim image only
            # from here on a runaway allocation is a MemoryError that stops this script, not
            # an out-of-memory kill of the whole run
            cap_memory(g["sandbox_memory_share"])
        try:
            compiled = compile(code, FILENAME, "exec")
            self._guarded(lambda: exec(compiled, self.globals))
        except ScriptStopped as exc:
            self._stop(ctx, str(exc))
            return
        except Exception as exc:
            self._stop(ctx, self._describe(exc))
            return
        fn = self.globals.get("on_step")
        if not callable(fn):
            self._stop(ctx, "it does not define on_step(view, act)")
            return
        self.on_step = fn
        if restore:
            self.globals.update(restore.get("state", {}))
            self.next_t = float(restore.get("next_t", self.next_t))
            self.spent_s = float(restore.get("spent_s", 0.0))
            self.calls = int(restore.get("calls", 0))
            self.acts_total = int(restore.get("acts_total", 0))
            self.added = int(restore.get("added", 0))
            if restore.get("stopped"):
                self.stopped = True
        ctx.log_event("script", ev, action="started", title=self.title)

    # ------------------------------------------------------------------ running
    def _guarded(self, fn: Any) -> None:
        deadline = time.perf_counter() + self.call_budget_s
        act_before = self.act_s
        lines = [0]

        def local(frame: Any, event: str, arg: Any) -> Any:
            lines[0] += 1
            if lines[0] > self.line_budget:
                raise ScriptStopped(f"one step ran more than {self.line_budget:,} lines")
            if time.perf_counter() - (self.act_s - act_before) > deadline:
                raise ScriptStopped(f"one step took longer than {self.call_budget_s * 1000:.0f} ms")
            return local

        def tracer(frame: Any, event: str, arg: Any) -> Any:
            return local if frame.f_code.co_filename == FILENAME else None

        old = sys.gettrace()
        sys.settrace(tracer)
        started = time.perf_counter()
        try:
            fn()
        finally:
            sys.settrace(old)
            self.spent_s += time.perf_counter() - started - (self.act_s - act_before)

    @staticmethod
    def _describe(exc: BaseException) -> str:
        if isinstance(exc, MemoryError):
            return "it tried to use more memory than the sandbox allows (MemoryError)"
        tb = exc.__traceback__
        line = None
        while tb is not None:
            if tb.tb_frame.f_code.co_filename == FILENAME:
                line = tb.tb_lineno
            tb = tb.tb_next
        where = f" on line {line}" if line else ""
        return f"{type(exc).__name__}{where}: {str(exc)[:120]}"

    def _stop(self, ctx: Any, reason: str) -> None:
        self.stopped = True
        ctx.note(f"scenario script stopped: {reason}")
        ctx.log_event("script", self.ev, action="stopped", title=self.title, reason=reason)

    def tick(self, ctx: Any) -> None:
        """Call on_step if it is due (at most once per frame)."""
        if self.stopped or self.on_step is None or ctx.t + 1e-9 < self.next_t:
            return
        while self.next_t <= ctx.t + 1e-9:
            self.next_t += self.every_s
        if self.spent_s > self.total_budget_s:
            self._stop(ctx, f"it used its {self.total_budget_s:g} s time budget")
            return
        view = self._view(ctx)
        self.acts_call = 0
        self.calls += 1
        try:
            self._guarded(lambda: self.on_step(view, self.act))
        except ScriptStopped as exc:
            self._stop(ctx, str(exc))
        except Exception as exc:
            self._stop(ctx, self._describe(exc))

    def snapshot(self) -> dict[str, Any]:
        """Script memory a checkpoint can keep (JSON-able globals only)."""
        state = {
            k: v
            for k, v in self.globals.items()
            if not k.startswith("__") and not callable(v) and _plain(v)
        }
        return {
            "event": self.ev,
            "state": json.loads(json.dumps(state)),
            "next_t": self.next_t,
            "spent_s": round(self.spent_s, 4),
            "calls": self.calls,
            "acts_total": self.acts_total,
            "added": self.added,
            "stopped": self.stopped,
        }

    # --------------------------------------------------------------------- view
    def _view(self, ctx: Any) -> types.SimpleNamespace:
        pos = np.asarray(ctx.live_positions(), dtype=float).reshape(-1, 2)
        xs, ys = pos[:, 0], pos[:, 1]
        zones: dict[str, dict[str, Any]] = {}
        for zid, area in ctx.zones.items():
            n = int(shapely.contains_xy(area, xs, ys).sum()) if len(xs) else 0
            zones[zid] = {
                "people": n,
                "density": round(n / area.area, 2) if area.area > 0 else 0.0,
            }
        exits: dict[str, dict[str, Any]] = {}
        near_areas = self.near_areas
        for eid, ex in ctx.exits.items():
            if ex.kind != "exit":
                continue
            cx, cy = ex.center
            r = NEAR_M + ex.width_m / 2
            if eid not in near_areas:
                near_areas[eid] = max(Point(cx, cy).buffer(r).intersection(ctx.free).area, 0.5)
            near = int((np.hypot(xs - cx, ys - cy) <= r).sum()) if len(xs) else 0
            exits[eid] = {
                "open": bool(ex.open),
                "people_near": near,
                "density": round(near / near_areas[eid], 2),
                "queue": int(ctx.load.get(eid, 0)) if ex.open else 0,
            }
        return types.SimpleNamespace(
            t=round(float(ctx.t), 2),
            zones=zones,
            exits=exits,
            people_inside=len(pos),
            zone_ids=tuple(zones),
            exit_ids=tuple(exits),
        )

    # ---------------------------------------------------------------------- act
    def _make_act(self, ctx: Any) -> types.SimpleNamespace:
        from plugins.events import close_exit_now, open_exit_now, slow_everyone, surge_step

        def timed(fn: Any) -> Any:
            def wrapper(*args: Any) -> None:
                started = time.perf_counter()
                try:
                    fn(*args)
                finally:
                    self.act_s += time.perf_counter() - started

            return wrapper

        def allowed(what: str) -> bool:
            if self.acts_call >= self.max_acts_step or self.acts_total >= self.max_acts_total:
                note(f"too many actions; {what} ignored")
                return False
            self.acts_call += 1
            self.acts_total += 1
            return True

        def log(action: str, **extra: Any) -> None:
            ctx.log_event("script", self.ev, action=action, title=self.title, **extra)

        def exit_of(exit_id: Any) -> Any:
            ex = ctx.exits.get(str(exit_id))
            if ex is None or ex.kind != "exit":
                note(f"there is no exit called '{exit_id}' on this floor")
                return None
            return ex

        def note(text: Any) -> None:
            if self.notes >= self.max_notes:
                return
            self.notes += 1
            ctx.note(f"Scenario script at {ctx.t:.0f} s: {str(text)[:140]}")
            log("note", text=str(text)[:140])

        def close_exit(exit_id: Any) -> None:
            ex = exit_of(exit_id)
            if ex is None or not ex.open or not allowed("close_exit"):
                return
            moved, trapped = close_exit_now(ctx, ex)
            ctx.note(
                f"Scenario script closed {ex.id} at {ctx.t:.0f} s: {moved} people rerouted"
                + (f", {trapped} trapped" if trapped else "")
            )
            log("close_exit", exit_id=ex.id, moved=moved, trapped=trapped)

        def open_exit(exit_id: Any) -> None:
            ex = exit_of(exit_id)
            if ex is None or ex.open or not allowed("open_exit"):
                return
            moved = open_exit_now(ctx, ex)
            ctx.note(f"Scenario script opened {ex.id} at {ctx.t:.0f} s: {moved} people turned")
            log("open_exit", exit_id=ex.id, moved=moved)

        def redirect(from_exit: Any, to_exit: Any, fraction: Any = 0.5) -> None:
            src, dst = exit_of(from_exit), exit_of(to_exit)
            if src is None or dst is None or not allowed("redirect"):
                return
            if not dst.open:
                note(f"cannot send people to {dst.id}: it is closed")
                return
            frac = min(max(float(fraction), 0.0), 1.0)
            cands = sorted(
                jid
                for jid, info in ctx.agents.items()
                if info.target == src.id and info.kind == "normal"
            )
            k = int(round(len(cands) * frac))
            chosen = ctx.rng.choice(np.asarray(cands), size=k, replace=False) if k else []
            for jid in chosen:
                ctx.switch(int(jid), dst.id)
            log("redirect", from_exit=src.id, to_exit=dst.id, fraction=frac, moved=k)
            if k:
                ctx.note(
                    f"Scenario script sent {k} people from {src.id} to {dst.id} at {ctx.t:.0f} s"
                )

        def add_people(zone_id: Any, n: Any) -> None:
            zid = str(zone_id)
            if zid not in ctx.zones:
                note(f"there is no zone called '{zone_id}' on this floor")
                return
            want = max(int(n), 0)
            room = self.max_added - self.added
            count = min(want, 500, room)
            if count <= 0 or not allowed("add_people"):
                if want > 0:
                    note(f"add_people ignored: at most {self.max_added} extra people per script")
                return
            self.added += count
            ctx.steps.append(surge_step(ctx, zid, count, f"script:{zid}"))
            log("add_people", zone_id=zid, people=count)
            ctx.note(f"Scenario script adds {count} people in {zid} at {ctx.t:.0f} s")

        def slow_down(factor: Any) -> None:
            f = float(factor)
            if not math.isfinite(f) or not allowed("slow_down"):
                return
            floor = self.min_speed_share
            f = min(max(f, floor), 1.0)
            # never past the floor in total, however often it is called
            share = max(self.speed_share * f, floor)
            f = share / self.speed_share
            if f > 0.999:
                note(f"slow_down ignored: people are already at {floor:.0%} speed")
                return
            self.speed_share = share
            affected = slow_everyone(ctx, f)
            log("slow_down", factor=f, affected=affected)
            ctx.note(
                f"Scenario script slowed everyone to {share:.0%} of normal speed at {ctx.t:.0f} s"
            )

        return types.SimpleNamespace(
            close_exit=timed(close_exit),
            open_exit=timed(open_exit),
            redirect=timed(redirect),
            add_people=timed(add_people),
            slow_down=timed(slow_down),
            note=timed(note),
        )
