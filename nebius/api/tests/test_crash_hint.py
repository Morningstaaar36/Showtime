"""Why a simulation container stopped without a result, in words that are true: exit 137 is a
SIGKILL, which is the memory limit or someone stopping the container; the runner can't tell which
(containers are removed on exit), so it names both."""

from __future__ import annotations

from api.adapters.sandbox import crash_hint


def test_exit_137_names_both_causes() -> None:
    hint = crash_hint(137, "")
    assert "out of memory" in hint and "stopped from outside" in hint


def test_another_exit_quotes_the_end_of_stderr() -> None:
    assert (
        crash_hint(1, "Traceback ...\nValueError: bad geometry\n")
        == "Traceback ...\nValueError: bad geometry"
    )
