"""Shared fixtures: a plugin host loaded from the real plugins/ folder."""

from __future__ import annotations

import os

import pytest

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
