"""Weather provider: Open-Meteo hourly wind gusts (forecast or archive), cached on disk.

Open-Meteo is free for non-commercial use; data CC BY 4.0 (https://open-meteo.com/en/terms).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from api.adapters.cache import DiskCache, cache_key

log = logging.getLogger("showtime.weather")


class WeatherUnavailable(Exception):
    """Forecast could not be fetched (offline, API error); the UI offers manual gust input."""


class OpenMeteoWeather:
    """Hourly `wind_gusts_10m` and `wind_speed_10m` in m/s for a location and date range."""

    kind = "weather"
    id = "open_meteo"
    label = "Open-Meteo"

    def __init__(
        self,
        forecast_url: str,
        archive_url: str,
        cache_dir: Path,
        offline: bool = False,
        timeout_s: float = 15.0,
    ) -> None:
        self.forecast_url = forecast_url
        self.archive_url = archive_url
        self.cache = DiskCache(cache_dir)
        self.offline = offline
        self.timeout_s = timeout_s
        self.calls = 0

    async def timezone_for(self, lat: float, lon: float) -> str:
        """IANA time zone of a point (Open-Meteo resolves it with timezone=auto); UTC if offline."""
        params: dict[str, str | float] = {
            "latitude": round(lat, 3),
            "longitude": round(lon, 3),
            "timezone": "auto",
            "hourly": "wind_speed_10m",
            "forecast_days": 1,
        }
        key = cache_key("open_meteo_tz", params)
        cached = self.cache.get(key)
        if cached is not None:
            return str(cached["timezone"])
        if self.offline:
            return "UTC"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.get(self.forecast_url, params=params)
            tz = str(resp.json().get("timezone") or "UTC") if resp.status_code == 200 else "UTC"
        except (httpx.HTTPError, ValueError):
            return "UTC"
        if tz != "UTC":
            self.cache.put(key, {"timezone": tz})
        return tz

    async def hourly_gusts(
        self, lat: float, lon: float, tz: str, start: date, days: int = 2
    ) -> dict[str, Any]:
        """{"times": [...local ISO...], "gust_ms": [...], "wind_ms": [...], "source": ...}."""
        end = start + timedelta(days=max(days, 1) - 1)
        use_archive = end < date.today() - timedelta(days=5)
        url = self.archive_url if use_archive else self.forecast_url
        params: dict[str, str | float] = {
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "hourly": "wind_speed_10m,wind_gusts_10m",
            "wind_speed_unit": "ms",
            "timezone": tz,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        key = cache_key("open_meteo", url, params)
        cached = self.cache.get(key)
        if cached is not None:
            return dict(cached, cached=True)
        if self.offline:
            raise WeatherUnavailable("Live weather is off (offline mode).")
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.get(url, params=params)
                self.calls += 1
            if resp.status_code != 200:
                raise WeatherUnavailable(
                    f"Open-Meteo returned {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
        except httpx.HTTPError as exc:
            raise WeatherUnavailable(f"Open-Meteo could not be reached: {exc}") from exc
        hourly = data.get("hourly") or {}
        out = {
            "times": hourly.get("time", []),
            "gust_ms": hourly.get("wind_gusts_10m", []),
            "wind_ms": hourly.get("wind_speed_10m", []),
            "timezone": data.get("timezone", tz),
            "source": "Open-Meteo archive (ERA5 reanalysis)"
            if use_archive
            else "Open-Meteo forecast",
            "source_url": "https://open-meteo.com/",
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "lat": lat,
            "lon": lon,
        }
        if not out["times"]:
            raise WeatherUnavailable("Open-Meteo returned no hourly data for that date.")
        self.cache.put(key, out)
        return dict(out, cached=False)
