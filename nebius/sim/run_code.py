"""Sandbox entry point for code jobs: python /app/run_code.py /work/<job_id>

Runs `<dir>/script.py` (AI- or user-written) with the data helper `showtime_data` importable
and the job's input files in `<dir>` (SHOWTIME_WORK). The script's result is, in order:
the return value of `main()` if it defines one, else a variable named `output`, else the JSON
it printed on its last line. That result is printed as JSON on the last stdout line.

Exit codes: 0 ok, 1 the script failed, 124 it ran out of time (SHOWTIME_TIMEOUT_S).
The container (no network, non-root, capped) is the security boundary, not this file.
"""

from __future__ import annotations

import io
import json
import math
import os
import signal
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

MAX_OUTPUT_CHARS = 200_000
MAX_ROWS = 500
MAX_ITEMS = 20_000
TIMEOUT_EXIT = 124


class _OutOfTime(BaseException):
    """Raised by the alarm; a BaseException so `except Exception` in a script can't swallow it."""


def _on_alarm(_signum: int, _frame: Any) -> None:
    raise _OutOfTime


def jsonable(value: Any, depth: int = 0) -> Any:
    """Plain JSON values from numpy/pandas objects (NaN and infinity become null)."""
    if depth > 12:
        return str(value)[:200]
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): jsonable(v, depth + 1) for k, v in list(value.items())[:MAX_ITEMS]}
    if isinstance(value, list | tuple | set):
        return [jsonable(v, depth + 1) for v in list(value)[:MAX_ITEMS]]
    mod = type(value).__module__.split(".")[0]
    if mod == "pandas":
        if hasattr(value, "to_dict") and hasattr(value, "columns"):  # DataFrame
            return jsonable(value.head(MAX_ROWS).to_dict(orient="records"), depth + 1)
        if hasattr(value, "to_dict"):  # Series
            return jsonable(value.head(MAX_ROWS).to_dict(), depth + 1)
        if hasattr(value, "isoformat"):
            return value.isoformat()
    if mod == "numpy" and hasattr(value, "tolist"):
        return jsonable(value.tolist(), depth + 1)
    if hasattr(value, "item"):
        try:
            return jsonable(value.item(), depth + 1)
        except (TypeError, ValueError):
            pass
    return str(value)[:200]


def _last_json_line(text: str) -> tuple[bool, Any, str]:
    """(found, value, text without that line) for the last non-empty printed line."""
    lines = text.rstrip("\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return False, None, text
    try:
        return True, json.loads(lines[-1]), "\n".join(lines[:-1])
    except ValueError:
        return False, None, text


def _script_traceback() -> str:
    """The traceback without this runner's own frames."""
    etype, exc, tb = sys.exc_info()
    frames = [f for f in traceback.extract_tb(tb) if f.filename == "script.py"]
    lines = traceback.format_list(frames[-5:])
    return "".join(lines) + "".join(traceback.format_exception_only(etype, exc))


def main(work: Path) -> int:
    os.environ["SHOWTIME_WORK"] = str(work)
    code = (work / "script.py").read_text()
    timeout = float(os.environ.get("SHOWTIME_TIMEOUT_S", "30"))
    captured = io.StringIO()
    ns: dict[str, Any] = {"__name__": "__main__"}
    signal.signal(signal.SIGALRM, _on_alarm)
    signal.setitimer(signal.ITIMER_REAL, max(timeout, 0.1))
    status = 0
    value: Any = None
    try:
        with redirect_stdout(captured):
            try:
                exec(compile(code, "script.py", "exec"), ns)  # sandboxed by design
                if callable(ns.get("main")):
                    value = ns["main"]()
                elif "output" in ns:
                    value = ns["output"]
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    status = 1
                    print(f"The script exited with code {exc.code}.", file=sys.stderr)
    except _OutOfTime:
        sys.stdout.write(captured.getvalue()[-4000:])
        print(f"The script ran longer than {timeout:g} s and was stopped.", file=sys.stderr)
        return TIMEOUT_EXIT
    except BaseException:  # the script's own error, reported in plain words
        signal.setitimer(signal.ITIMER_REAL, 0)
        sys.stdout.write(captured.getvalue()[-4000:])
        print(_script_traceback(), file=sys.stderr)
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    printed = captured.getvalue()
    if status == 0 and value is None and "main" not in ns and "output" not in ns:
        found, value, printed = _last_json_line(printed)
        if not found:
            value = None
    try:
        text = json.dumps(jsonable(value), allow_nan=False)
    except (TypeError, ValueError) as exc:
        print(f"The result could not be turned into JSON: {exc}", file=sys.stderr)
        return 1
    if len(text) > MAX_OUTPUT_CHARS:
        print(
            f"The result is too large ({len(text)} characters; the limit is "
            f"{MAX_OUTPUT_CHARS}). Return a summary or fewer rows.",
            file=sys.stderr,
        )
        return 1
    if printed.strip():
        sys.stdout.write(printed[-8000:].rstrip("\n") + "\n")
    sys.stdout.write(text + "\n")
    sys.stdout.flush()
    return status


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "/work")))
