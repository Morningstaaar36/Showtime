"""Shared fixtures: a plugin host loaded from the real plugins/ folder."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

# Tests never touch the app's own database or run folders: a running app shares them, and a
# test that builds the app state (which marks "interrupted" sessions as stopped at start) would
# stop the app's live tests.
os.environ.setdefault("SHOWTIME_TEST_DIR", tempfile.mkdtemp(prefix="showtime-tests-"))
os.environ.setdefault("DB_URL", f"sqlite:///{os.environ['SHOWTIME_TEST_DIR']}/tests.sqlite")
os.environ.setdefault("RUNS_DIR", f"{os.environ['SHOWTIME_TEST_DIR']}/runs")
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("SANDBOX_PROVIDER", "fake")
os.environ.setdefault("LLM_CACHE_MODE", "off")
os.environ.setdefault("TAVILY_API_KEY", "")
os.environ.setdefault("OFFLINE", "true")

from api.core.extensions import Registry
from api.core.plugins import PluginHost, load_plugins
from api.core.settings import ROOT_DIR
from api.core.templates import get_template
from api.models import Venue


@pytest.fixture
def cloud_sandbox() -> Iterator[str]:
    """A sandbox provider that needs a key (registered for one test): "cloudbox", which is not
    configured while OPENAI_COMPAT_API_KEY is empty and runs the fake runner once it is."""
    from api.adapters.providers import SANDBOX, sandbox_provider
    from api.adapters.providers.base import Requirement

    fake = sandbox_provider("fake")
    SANDBOX.register(
        type(fake)(
            kind="sandbox",
            name="cloudbox",
            title="Cloud sandbox",
            requirements=(
                Requirement("OPENAI_COMPAT_API_KEY", "openai_compat_api_key", "a key", True),
            ),
            build=fake.build,
        )
    )
    try:
        yield "cloudbox"
    finally:
        SANDBOX.unregister("cloudbox")


@pytest.fixture(scope="session")
def host() -> PluginHost:
    return load_plugins(ROOT_DIR)


@pytest.fixture(scope="session")
def registry(host: PluginHost) -> Registry:
    return host.registry


@pytest.fixture
def hall() -> Venue:
    return get_template("conference_hall_2f")


@pytest.fixture
def field() -> Venue:
    return get_template("festival_field")


@pytest.fixture
def school() -> Venue:
    return get_template("school_wing")


@pytest.fixture
def alley() -> Venue:
    return get_template("t_alley")
