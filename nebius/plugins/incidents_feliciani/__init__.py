"""Incident data for the red team (IncidentSource).

Primary data: Claudio Feliciani, "List of crowd accidents from 1900 to 2024",
https://doi.org/10.5281/zenodo.19483010, CC BY 4.0, downloaded by scripts/get_data.sh.
A curated seed list of well-known incidents (Wikipedia links) is always available, so
the red team works before the download and offline.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from api.core.extensions import IncidentRecord, Registry

ROOT = Path(__file__).resolve().parents[2]
SEED = Path(__file__).resolve().parent / "seed.json"
DATASET_LABEL = "Feliciani crowd-accident list (Zenodo, CC BY 4.0)"


class Config(BaseModel):
    """Where the normalised dataset lives (relative to the project root)."""

    data_file: str = "data/incidents/incidents.json"
    use_seed: bool = True


def _name(r: dict[str, Any]) -> str:
    kind = {
        "Religious": "Religious gathering",
        "Sport": "Sports event",
        "Entertainment": "Entertainment event",
        "Charity": "Charity distribution",
        "Political": "Political rally",
        "Educational": "School event",
        "Transportation": "Transport hub",
        "Shopping": "Shopping event",
        "Application": "Application queue",
    }.get(r.get("event_type", ""), "Crowd gathering")
    return f"{kind} crush, {r.get('country') or 'unknown country'} {r.get('year') or ''}".strip()


class FelicianiIncidents:
    """Search real incidents by venue features."""

    id = "incidents_feliciani"
    label = "Crowd accidents 1900–2024"
    citation = "Feliciani et al., crowd accidents 1900–2024 dataset"
    citation_url = "https://doi.org/10.5281/zenodo.19483010"

    def __init__(self, config: Config) -> None:
        self.config = config
        self._records: list[IncidentRecord] | None = None
        self.dataset_loaded = False

    def _load(self) -> list[IncidentRecord]:
        if self._records is not None:
            return self._records
        out: list[IncidentRecord] = []
        path = ROOT / self.config.data_file
        if path.exists():
            data = json.loads(path.read_text())
            for r in data.get("records", []):
                out.append(
                    IncidentRecord.model_validate(
                        {
                            **{
                                k: r.get(k)
                                for k in (
                                    "row_id",
                                    "year",
                                    "country",
                                    "event_type",
                                    "deaths",
                                    "injuries",
                                    "description",
                                    "source_url",
                                    "setting",
                                    "date",
                                    "crowd_size",
                                    "dataset_url",
                                )
                            },
                            "city": "",
                            "keywords": r.get("keywords", []),
                            "name": _name(r),
                            "dataset": DATASET_LABEL,
                        }
                    )
                )
            self.dataset_loaded = True
        if self.config.use_seed and SEED.exists():
            for r in json.loads(SEED.read_text())["records"]:
                rec = IncidentRecord.model_validate({**r, "dataset": "Curated list (Wikipedia)"})
                twin = self._twin(out, rec)
                if twin is not None:
                    # same incident in the dataset: keep the dataset row, borrow the name
                    twin.name = rec.name
                    twin.keywords = sorted(set(twin.keywords) | set(rec.keywords))
                    if "wikipedia.org" in rec.source_url:
                        twin.source_url = rec.source_url
                    continue
                out.append(rec)
        self._records = out
        return out

    @staticmethod
    def _twin(rows: list[IncidentRecord], rec: IncidentRecord) -> IncidentRecord | None:
        for r in rows:
            if r.year != rec.year or not r.country or not rec.country:
                continue
            if r.country.split()[0].lower() != rec.country.split()[0].lower():
                continue
            if r.deaths and rec.deaths and abs(r.deaths - rec.deaths) <= max(5, 0.25 * rec.deaths):
                return r
        return None

    def count(self) -> int:
        return len(self._load())

    def get(self, row_id: int) -> IncidentRecord | None:
        """One record by id."""
        return next((r for r in self._load() if r.row_id == row_id), None)

    def search(self, features: dict[str, Any], limit: int) -> list[IncidentRecord]:
        """Most relevant incidents: keyword overlap, setting, severity, documentation."""
        want: dict[str, float] = dict(features.get("keywords", {}))
        settings: list[str] = list(features.get("settings", []))
        exclude: set[int] = set(features.get("exclude_ids", []))
        scored: list[tuple[float, IncidentRecord]] = []
        for r in self._load():
            if r.row_id in exclude:
                continue
            s = sum(w for k, w in want.items() if k in r.keywords)
            if r.setting in settings:
                s += 2.0 * (len(settings) - settings.index(r.setting)) / len(settings)
            if r.deaths:
                s += 0.35 * math.log10(1 + r.deaths)
            if r.year and r.year >= 1980:
                s += 0.4
            if "wikipedia.org" in r.source_url:
                s += 0.5
            if s > 0:
                scored.append((s, r))
        scored.sort(key=lambda x: (-x[0], -(x[1].year or 0), x[1].row_id))
        picked: list[IncidentRecord] = []
        per_setting: dict[str, int] = {}
        for _, r in scored:
            if per_setting.get(r.setting, 0) >= max(2, limit // 2):
                continue
            picked.append(r)
            per_setting[r.setting] = per_setting.get(r.setting, 0) + 1
            if len(picked) >= limit:
                break
        return picked


def showtime_register(registry: Registry, config: Config) -> None:
    """Register the incident source."""
    registry.add("IncidentSource", FelicianiIncidents.id, FelicianiIncidents(config))
