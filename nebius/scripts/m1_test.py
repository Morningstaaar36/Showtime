"""Local M1 test launcher. Requires only host Python 3 and Docker Desktop.

Usage: python3 scripts/m1_test.py {init,up,down,status,logs,smoke} [--no-build]
Application dependencies are installed in containers, never in the host Python.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8000/api/v1"
WEB = "http://127.0.0.1:5173"


def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def compose(*args: str) -> None:
    env = os.environ.copy()
    # The API asks the host daemon to mount this path into sibling sim containers.
    env["HOST_RUNS_DIR"] = str(ROOT / "runs")
    env.pop("DOCKER_DEFAULT_PLATFORM", None)
    run(
        [
            "docker",
            "compose",
            "-p",
            "showtime",
            "--project-directory",
            str(ROOT),
            "-f",
            str(ROOT / "docker-compose.yml"),
            "-f",
            str(ROOT / "docker-compose.m1-test.yml"),
            *args,
        ],
        env=env,
    )


def init() -> None:
    for name in ("runs", "cache", "state", "data", "logs"):
        (ROOT / name).mkdir(exist_ok=True)
    target = ROOT / ".env"
    if not target.exists():
        with target.open("x") as output:
            output.write((ROOT / "config/m1-test.env.example").read_text())
        target.chmod(0o600)
        print("Created .env for the local M1 test profile (OpenRouter and Docker).", flush=True)
    else:
        print("Using existing .env (settings preserved).", flush=True)
    print(
        "AI calls need OPENAI_COMPAT_API_KEY in .env. Templates and simulations need no key.",
        flush=True,
    )


def setting(name: str, default: str = "") -> str:
    if name in os.environ:
        return os.environ[name]
    path = ROOT / ".env"
    if path.exists():
        for line in reversed(path.read_text().splitlines()):
            key, sep, value = line.strip().partition("=")
            if sep and key == name:
                return value.split(" #", 1)[0].strip().strip("\"'")
    return default


def docker_ready(start: bool = False) -> None:
    if not shutil.which("docker"):
        raise RuntimeError("Install Docker Desktop for Apple Silicon, then run make m1-test-up.")
    deadline = time.monotonic() + (120 if start else 1)
    opened = False
    while True:
        try:
            result = subprocess.run(["docker", "info"], capture_output=True, timeout=15)
            ready = result.returncode == 0
        except subprocess.TimeoutExpired:
            ready = False
        if ready:
            run(["docker", "compose", "version"], stdout=subprocess.DEVNULL)
            return
        if not start or time.monotonic() >= deadline:
            raise RuntimeError("Docker Desktop is unavailable. Start it and retry.")
        if not opened:
            print("Starting Docker Desktop…", flush=True)
            run(["open", "-a", "Docker"])
            opened = True
        time.sleep(2)


def call(method: str, path: str, body: Any = None, timeout: float = 30) -> Any:
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-Showtime": "1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read()
        return json.loads(data) if data else None


def status() -> None:
    compose("ps")
    health = call("GET", "/health")
    for name, provider in health["providers"].items():
        state = "available" if provider["ok"] else "unavailable"
        # Avoid printing raw provider error strings, which may contain credentials/URLs.
        print(f"{name}: {state}")
    print("Model status checks the catalog; completion success and quota require an AI request.")
    if not health["providers"]["llm"]["ok"]:
        print("AI unavailable: check .env key, MODEL_* IDs, and OpenRouter quota.")
    print(f"Showtime: {WEB}  |  API docs: http://127.0.0.1:8000/api/docs")


def up(build: bool = True) -> None:
    init()
    docker_ready(start=True)
    sim_platform = setting("SIM_PLATFORM", "linux/amd64") or "linux/amd64"
    image = setting("SIM_IMAGE", "showtime-sim:latest") or "showtime-sim:latest"
    if build:
        print(f"Building simulation image for {sim_platform}…", flush=True)
        run(["docker", "build", "--platform", sim_platform, "-t", image, "sim/"])
        compose("build")
    else:
        for required in (image, "showtime-api:latest", "showtime-web:latest"):
            result = subprocess.run(
                ["docker", "image", "inspect", required],
                capture_output=True,
                timeout=15,
            )
            if result.returncode:
                raise RuntimeError(
                    f"Image {required} is missing. Build first with make m1-test-up."
                )
    compose("up", "-d", "--wait", "--wait-timeout", "180", "--force-recreate", "--pull", "never")
    # Provider readiness is distinct from server readiness. Missing credentials do not
    # prevent exploring the editor, saved examples, or real local simulations.
    status()


def smoke() -> None:
    """Exercise real host-path mounting and simulation; consumes no model quota."""
    with urllib.request.urlopen(WEB, timeout=10) as response:
        if response.status != 200 or b"<html" not in response.read().lower():
            raise RuntimeError("The web UI did not return HTML.")
    with urllib.request.urlopen(WEB + "/api/v1/templates", timeout=10) as response:
        if not json.load(response):
            raise RuntimeError("The web-to-API proxy returned no templates.")
    health = call("GET", "/health")
    if not health["providers"]["sandbox"]["ok"]:
        raise RuntimeError("The simulation provider is unavailable. Run make m1-test-up.")

    def rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]

    venue = {
        "venue_id": "m1_test_smoke",
        "name": "M1 test startup check",
        "mode": "indoor",
        "floors": [
            {
                "floor_id": "F0",
                "elevation_m": 0,
                "walkable": rect(0, 0, 12, 10),
                "obstacles": [],
                "exits": [{"id": "E1", "polygon": rect(4, 0.02, 6, 0.42), "width_m": 2}],
                "zones": [{"id": "Z1", "polygon": rect(1, 5, 9, 9), "people": 20}],
            }
        ],
        "stairs": [],
    }
    project = call("POST", "/projects", {"name": "M1 test startup check", "venue": venue})
    run_id = None
    finished = False
    try:
        call(
            "POST",
            f"/projects/{project['id']}/patch",
            {
                "patch": {"ops": [{"op": "resize", "target": "E1", "width_m": 1.8}]},
                "message": "M1 test manual-edit check",
            },
        )
        saved = call("GET", f"/projects/{project['id']}")
        if saved["version"]["venue"]["floors"][0]["exits"][0]["width_m"] != 1.8:
            raise RuntimeError("The manual exit edit was not saved.")
        row = call(
            "POST",
            "/runs",
            {
                "project_id": project["id"],
                "tier": 2,
                "seed": time.time_ns() % 2**31,
            },
        )
        run_id = row["id"]
        print(f"Checking real simulation {run_id}…", flush=True)
        deadline = time.monotonic() + 180
        while row["status"] in ("queued", "running"):
            if time.monotonic() > deadline:
                raise RuntimeError("Simulation check exceeded 180 seconds.")
            time.sleep(2)
            row = call("GET", f"/runs/{run_id}")
        finished = True
        result = row.get("result") or {}
        if (
            row["status"] != "ok"
            or result.get("provider") != "docker"
            or result.get("engine") != "jupedsim"
        ):
            raise RuntimeError(f"Real simulation did not complete: {row['status']} ({run_id}).")
        metrics = result["metrics"]
        if metrics["agents_total"] != 20 or metrics["agents_not_evacuated"] != 0:
            raise RuntimeError("The 20-person simulation did not clear the room.")
        artifacts = result.get("artifacts", {})
        if not artifacts.get("trajectory") or not artifacts.get("density_grid"):
            raise RuntimeError("Simulation produced no trajectory or density artifacts.")
        for kind in ("trajectory", "density"):
            with urllib.request.urlopen(f"{API}/runs/{run_id}/{kind}", timeout=10) as response:
                if not response.read():
                    raise RuntimeError(f"Simulation {kind} artifact is empty.")
        print(
            f"PASS: UI, API proxy, saved manual edit, and real Docker simulation; "
            f"20 people cleared, 95% out in {metrics['evac_time_p95_s']:.1f}s."
        )
    finally:
        if run_id and not finished:
            call("POST", f"/runs/{run_id}/cancel")
        call("DELETE", f"/projects/{project['id']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "up", "down", "status", "logs", "smoke"])
    parser.add_argument(
        "--no-build", action="store_true", help="Start existing images without downloads"
    )
    args = parser.parse_args()
    try:
        if args.action == "init":
            init()
            return 0
        if platform.system() != "Darwin" or platform.machine() not in ("arm64", "aarch64"):
            raise RuntimeError("These targets are for Apple Silicon Macs; use make up on Linux.")
        if args.action == "up":
            up(build=not args.no_build)
        else:
            docker_ready()
            if args.action == "down":
                compose("down")
            elif args.action == "logs":
                compose("logs", "--tail=100", "-f", "api", "web")
            elif args.action == "status":
                status()
            else:
                smoke()
        return 0
    except urllib.error.HTTPError as exc:
        print(f"API request failed (HTTP {exc.code}). See make m1-test-logs.", file=sys.stderr)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        print(f"Startup/check failed: {exc}", file=sys.stderr)
        print("See make m1-test-logs for service output.", file=sys.stderr)
    except KeyboardInterrupt:
        return 130
    return 1


if __name__ == "__main__":
    sys.exit(main())
