"""Normalise the Feliciani crowd-accident list into data/incidents/incidents.json.

Input (from scripts/get_data.sh): accident_data_numeric.csv and references.zip from
https://doi.org/10.5281/zenodo.19483010 (CC BY 4.0, Claudio Feliciani).
Output: one record per accident with year, country, event type, deaths, injuries, crowd
size, description, cause keywords, setting and the press source URLs.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "incidents"
OUT = SRC / "incidents.json"
DOI = "10.5281/zenodo.19483010"

KEYWORDS: dict[str, str] = {
    "stairs": r"\bstair|\bsteps\b",
    "narrow": r"\bnarrow",
    "alley": r"\balley|\blane\b",
    "slope": r"\bslope|\bsloped|\buphill|\bdownhill|\bincline",
    "bridge": r"\bbridge|\bfootbridge|\boverpass",
    "tunnel": r"\btunnel|\bunderpass",
    "ramp": r"\bramp\b",
    "gate": r"\bgates?\b",
    "door": r"\bdoors?\b|\bdoorway",
    "exit": r"\bexits?\b",
    "locked_exit": r"\blocked\b|\bclosed (?:gate|door|exit)|\bshut\b",
    "single_exit": r"only (?:one )?(?:exit|door|gate)|single (?:exit|door|gate)|one exit",
    "fire": r"\bfire\b|\bblaze|\bsmoke\b|\bflames",
    "false_alarm": r"false alarm|misheard|rumou?r|mistaken",
    "panic": r"\bpanic",
    "counterflow": r"opposite direction|both (?:sides|directions|ends)|two directions|"
    r"counter[- ]?flow|other direction|against the flow",
    "surge": r"\bsurge|\bsurged|\brushed\b|\brush\b|\bpushed|\bpushing",
    "stage": r"\bstage\b",
    "wind": r"\bwind\b|\bstorm|\bgust|\btornado",
    "rain": r"\brain\b|\btook shelter",
    "tear_gas": r"tear ?gas|pepper spray",
    "police": r"\bpolice|\bsecurity\b",
    "overcrowding": r"overcrowd|capacity|too many people|more people than",
    "free_distribution": r"\bfree\b|distribution|handout|giveaway|donation|charity|food",
    "collapse": r"collaps",
    "barrier": r"barrier|fence|railing",
    "stadium": r"stadium|football|soccer|\bmatch\b",
    "religious": r"temple|shrine|mosque|church|pilgrim|religious|ritual|prayer",
    "station": r"station|\btrain|railway|platform|subway|\bmetro",
    "concert": r"concert|music|\bshow\b|performance|singer|band\b",
    "nightclub": r"nightclub|\bclub\b|disco",
    "school": r"\bschool|students|pupils",
    "street": r"\bstreet|\broad\b|\bsquare\b|\bplaza|\bparade",
    "celebration": r"new year|halloween|celebration|holiday|festival|carnival",
}
INDOOR_HINTS = (
    r"\bnightclub",
    r"\bschool\b",
    r"\bhall\b",
    r"\btheat(?:re|er)",
    r"\bcinema",
    r"\bauditorium",
    r"\bgymnasium",
    r"\bmall\b",
    r"\bindoors?\b",
    r"\bshelter\b",
    r"\barena\b",
    r"\bcoliseum",
    r"\bballroom",
)
PREFERRED = (
    "wikipedia.org",
    "bbc.",
    "reuters.com",
    "apnews.com",
    "theguardian.com",
    "nytimes.com",
    "aljazeera.com",
    "cnn.com",
    "france24.com",
    "dw.com",
)


def keywords_for(text: str) -> list[str]:
    """Cause and setting keywords found in a description."""
    low = text.lower()
    return sorted(k for k, pat in KEYWORDS.items() if re.search(pat, low))


def setting_for(kw: list[str], purpose: str, text: str) -> str:
    """Coarse setting used to match venues."""
    low = text.lower()
    if "stadium" in kw:
        return "stadium"
    if "station" in kw or "bridge" in kw:
        return "transport"
    if "nightclub" in kw:
        return "indoor"
    if "alley" in kw or ("street" in kw and "narrow" in kw):
        return "street"
    if any(re.search(h, low) for h in INDOOR_HINTS):
        return "indoor"
    if "religious" in kw or purpose == "Religious":
        return "religious"
    if "street" in kw:
        return "street"
    return "outdoor"


def pick_source(urls: list[str]) -> str | None:
    """Prefer encyclopaedic and wire-service sources."""
    for dom in PREFERRED:
        for u in urls:
            if dom in u:
                return u
    return urls[0] if urls else None


def _int(v: str) -> int | None:
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return None if n < 0 else n


def main() -> int:
    csv_path = SRC / "accident_data_numeric.csv"
    if not csv_path.exists():
        print("missing", csv_path, "- run scripts/get_data.sh", file=sys.stderr)
        return 1
    refs: dict[str, list[str]] = {}
    zpath = SRC / "references.zip"
    if zpath.exists():
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():
                if name.endswith(".txt"):
                    txt = z.read(name).decode("utf-8", errors="replace")
                    refs[Path(name).name] = re.findall(r"https?://\S+", txt)
    records = []
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            rid = int(row["Number"])
            desc = " ".join((row.get("Description") or "").split())
            purpose = row.get("Purpose of gathering") or ""
            kw = keywords_for(desc)
            urls = refs.get((row.get("References") or "").strip(), [])
            y, m, d = (
                _int(row.get("Year", "")),
                _int(row.get("Month", "")),
                _int(row.get("Day", "")),
            )
            iso = f"{y:04d}-{m:02d}-{d:02d}" if y and m and d else None
            records.append(
                {
                    "row_id": rid,
                    "date": iso,
                    "year": y,
                    "country": row.get("Country name") or "",
                    "country_code": row.get("Country code"),
                    "lat": float(row["Latitude"]) if row.get("Latitude") else None,
                    "lon": float(row["Longitude"]) if row.get("Longitude") else None,
                    "event_type": purpose,
                    "deaths": _int(row.get("Fatalities", "")),
                    "injuries": _int(row.get("Injured", "")),
                    "crowd_size": _int(row.get("Crowd size", "")),
                    "description": desc,
                    "keywords": kw,
                    "setting": setting_for(kw, purpose, desc),
                    "source_url": pick_source(urls) or f"https://doi.org/{DOI}#row={rid}",
                    "sources": urls[:6],
                    "dataset_url": f"https://doi.org/{DOI}#row={rid}",
                }
            )
    OUT.write_text(
        json.dumps(
            {
                "source": {
                    "title": "List of crowd accidents from 1900 to 2024",
                    "author": "Claudio Feliciani",
                    "doi": DOI,
                    "url": f"https://doi.org/{DOI}",
                    "license": "CC BY 4.0",
                    "retrieved": date.today().isoformat(),
                },
                "records": records,
            },
            ensure_ascii=False,
        )
    )
    print(f"wrote {len(records)} incidents to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
