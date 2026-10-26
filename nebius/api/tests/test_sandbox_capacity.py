"""How many runs a sandbox takes at once drives the sweep's tier and the default seed count:
a capability of the runner, never its provider's name."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from api.adapters.sandbox import DockerRunner, FakeRunner
from api.core.settings import Settings
from api.orchestrator.seeds import default_extra
from api.orchestrator.sweep import sweep_tier


def _st(runner: Any, **kw: Any) -> Any:
    return SimpleNamespace(runner=runner, settings=Settings(_env_file=None, **kw))


def test_one_sandbox_at_a_time_gets_quick_sweeps_and_fewer_seeds(tmp_path: Path) -> None:
    st = _st(DockerRunner(tmp_path, "img", "1g", 1.0, max_parallel=1))
    assert st.runner.parallel == 1
    assert sweep_tier(st) == 2
    assert default_extra(st) == st.settings.seeds_extra_serial


def test_parallel_sandboxes_get_full_sweeps_and_more_seeds_whatever_the_provider(
    tmp_path: Path,
) -> None:
    for runner in (DockerRunner(tmp_path, "img", "1g", 1.0, max_parallel=4), FakeRunner(tmp_path)):
        st = _st(runner, seeds_extra_parallel=4)
        assert st.runner.parallel > 1
        assert sweep_tier(st) == 3
        assert default_extra(st) == 4
