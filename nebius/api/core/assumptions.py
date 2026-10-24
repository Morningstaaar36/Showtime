"""Every default value that shapes a result, with its source (shown in reports and docs)."""

from __future__ import annotations

from typing import Any


def assumptions(settings: Any) -> list[dict[str, str]]:
    """Assumption rows: name, value, source."""
    s = settings
    return [
        {
            "name": "Walking speed",
            "value": f"{s.walk_speed_mean} ± {s.walk_speed_sd} m/s, "
            f"{int(s.slow_walker_fraction * 100)}% slow walkers (0.7 m/s)",
            "source": "Weidmann (1993) free walking speed 1.34 m/s; SFPE Handbook ch. 59",
        },
        {
            "name": "Body size",
            "value": f"radius {s.agent_radius} m",
            "source": "Calibrated so jam density matches Weidmann's 5.4 people per m² (docs/PROGRESS.md)",
        },
        {
            "name": "Exit capacity (instant estimate)",
            "value": f"{s.specific_flow} people per metre per second",
            "source": "SFPE Handbook maximum specific flow 1.3 p/(m·s)",
        },
        {
            "name": "Stairs",
            "value": f"{s.stair_speed} m/s along the stair, {s.stair_flow} people per metre per second",
            "source": "SFPE Handbook stair speeds and flows (conservative values)",
        },
        {
            "name": "Crowd pressure (turbulence)",
            "value": "local density × local velocity variance; turbulent above 0.02 per s², "
            f"reported where density is at least {s.density_warn_ppm2} people per m²",
            "source": "Helbing, Johansson & Al-Abideen (2007), Phys. Rev. E 75, 046109",
        },
        {
            "name": "Level of service",
            "value": "Fruin walkway bands A–F (F above about 2.2 people per m²)",
            "source": "Fruin (1971), Pedestrian Planning and Design",
        },
        {
            "name": "Warning and danger density",
            "value": f"{s.density_warn_ppm2} and {s.density_danger_ppm2} people per m²"
            f" (danger counts when sustained ≥ {s.danger_min_duration_s:g} s)",
            "source": "Fruin level of service F; Still (2014) crowd crush risk above about 5 people per m²",
        },
        {
            "name": "Evacuation target without a hazard",
            "value": f"indoor {s.target_evac_indoor_s / 60:.0f} min, "
            f"open-air {s.target_evac_outdoor_s / 60:.0f} min (× safety factor)",
            "source": "Planning targets (configurable); open-air follows UK Green Guide 8-minute egress practice",
        },
        {
            "name": "Pre-movement time",
            "value": f"{s.pre_movement_s:.0f} s",
            "source": "User setting (default 60 s)",
        },
        {
            "name": "Safety factor",
            "value": f"× {s.safety_factor}",
            "source": "User setting (default 1.5)",
        },
        {
            "name": "Crowd model",
            "value": "JuPedSim collision-free speed model, Δt 0.025–0.05 s",
            "source": "JuPedSim 1.4 (Tordeux et al. 2016); Δt calibration in docs/PROGRESS.md",
        },
        {
            "name": "Wind pressure",
            "value": "q = 0.613·Kz·Kzt·Kd·V², Kz 1.0, Kd 0.85, G 0.85",
            "source": "ASCE 7 velocity pressure form; screening estimate only",
        },
        {
            "name": "Weather",
            "value": "Hourly gusts at 10 m (Open-Meteo forecast or ERA5 archive)",
            "source": "Open-Meteo, CC BY 4.0; reanalysis smooths thunderstorm downbursts",
        },
        {
            "name": "Incident data",
            "value": "388 crowd accidents 1900–2024",
            "source": "Feliciani et al., Zenodo 10.5281/zenodo.19483010 (CC BY 4.0)",
        },
    ]
