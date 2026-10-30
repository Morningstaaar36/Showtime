"""Environment probe: GPU, Docker, LLM (chat + JSON), sim image, Tier 1, stage check, weather, search.

Read-only: does not touch the database. Usage: make probe
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import time
from datetime import date
from typing import Any

from pydantic import BaseModel

from api.adapters.llm import LLMClient
from api.adapters.search import TavilySearch
from api.adapters.weather import OpenMeteoWeather
from api.app.state import build_runner
from api.core.plugins import load_plugins
from api.core.settings import ROOT_DIR, Settings
from api.core.templates import get_template
from api.core.tier1 import run_tier1

GREEN, RED, AMBER, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
results: list[bool] = []


def report(name: str, ok: bool | None, detail: str) -> None:
    """Print one line; None means skipped (not a failure)."""
    mark = f"{GREEN}ok  {OFF}" if ok else f"{AMBER}skip{OFF}" if ok is None else f"{RED}FAIL{OFF}"
    print(f"  {mark} {name:<18} {detail}")
    if ok is not None:
        results.append(ok)


def sh(*cmd: str, timeout: float = 60) -> tuple[int, str]:
    """Run a command, return (code, combined output)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


class _Probe(BaseModel):
    answer: str
    confidence: float


async def main() -> int:
    st = Settings()
    print("Showtime probe\n")

    if shutil.which("nvidia-smi"):
        code, out = sh(
            "nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader"
        )
        report("GPU", code == 0, out.splitlines()[0] if out else "no output")
    else:
        report("GPU", None, "nvidia-smi not found (a hosted LLM provider does not need a GPU)")

    code, out = sh("docker", "version", "--format", "{{.Server.Version}}")
    report("Docker", code == 0, f"server {out}" if code == 0 else out[:120])

    runner = build_runner(st)
    h = await runner.health()
    report("Sandbox", bool(h.get("ok")), f"{st.sandbox_provider}: {h.get('detail', '')}")
    if runner.isolation.kind == "container" and code == 0:  # a local container sandbox
        code2, out2 = sh(
            "docker",
            "run",
            "--rm",
            "--network=none",
            st.sim_image,
            "python",
            "-c",
            "import jupedsim, pedpy, shapely; print(jupedsim.__version__, pedpy.__version__)",
        )
        report("Sim image", code2 == 0, f"jupedsim/pedpy {out2.splitlines()[-1] if out2 else ''}")

    llm = LLMClient(st.model_copy(update={"llm_cache_mode": "off"}))
    h = await llm.health()
    report("LLM server", bool(h.get("ok")), str(h.get("detail", "")))
    if h.get("ok"):
        t0 = time.perf_counter()
        r = await llm.chat(
            "fast",
            [{"role": "user", "content": "Reply with the single word: ready"}],
            max_tokens=16,
        )
        report(
            "LLM chat",
            "ready" in (r.text or "").lower(),
            f"{(r.text or '').strip()[:30]!r} in {time.perf_counter() - t0:.1f} s",
        )
        t0 = time.perf_counter()
        try:
            j = await llm.chat(
                "fast",
                [
                    {
                        "role": "user",
                        "content": "Is 5 people per m2 a dangerous crowd density? Answer briefly.",
                    }
                ],
                schema=_Probe,
                max_tokens=200,
            )
            report(
                "LLM JSON",
                isinstance(j.parsed, _Probe),
                f"schema-valid in {time.perf_counter() - t0:.1f} s",
            )
        except Exception as e:
            report("LLM JSON", False, str(e)[:120])

    host = load_plugins(ROOT_DIR)
    venue = get_template("conference_hall_2f")
    t0 = time.perf_counter()
    est = run_tier1(venue, [], host.registry, st)
    ms = (time.perf_counter() - t0) * 1000
    report("Tier 1", True, f"hall p95 {est.metrics.evac_time_p95_s:.0f} s in {ms:.0f} ms")

    try:
        from plugins.hazard_wind.stage_check import check_stage

        stage = get_template("festival_field").stage
        if stage is not None:
            sc = check_stage(stage)
            report(
                "Stage check",
                sc.v_limit_ms > 0,
                f"Pynite: limit {sc.v_limit_ms:.1f} m/s ({sc.governing})",
            )
    except Exception as e:
        report("Stage check", False, str(e)[:120])

    weather = OpenMeteoWeather(
        st.weather_base_url, st.weather_archive_url, st.cache_dir / "weather", offline=st.offline
    )
    try:
        w: dict[str, Any] = await weather.hourly_gusts(
            23.81, 90.41, "Asia/Dhaka", date.today(), days=1
        )
        report("Open-Meteo", bool(w.get("gust_ms")), f"{len(w.get('gust_ms', []))} hourly gusts")
    except Exception as e:
        report("Open-Meteo", None if st.offline else False, str(e)[:120])

    search = TavilySearch(st.tavily_api_key, st.cache_dir / "tavily", offline=st.offline)
    if not st.tavily_api_key:
        report("Tavily", None, "skipped: no key (red team uses the incident dataset)")
    else:
        h = await search.health()
        report("Tavily", bool(h.get("ok")), str(h.get("detail", "")))

    incidents = ROOT_DIR / "data" / "incidents" / "incidents.json"
    report(
        "Incident data",
        incidents.exists() or None,
        "found" if incidents.exists() else "missing: run make get-data (seed list used)",
    )

    ok = all(results)
    print(f"\n{GREEN + 'All checks passed.' if ok else RED + 'Some checks failed.'}{OFF}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
