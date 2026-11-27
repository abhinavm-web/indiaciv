"""Oil and gas extraction blocks and fields in India, from Global Energy Monitor's Global Oil and Gas Extraction
Tracker (GOGET), as published with GEM's public interactive map (data file dated August 2023).

GOGET puts an asset with no known location at the centre of its country; those placeholder points (the same
coordinates shared by several Indian assets) are kept in the raw file but are not placed on the map. GOGET covers
only extraction sites producing more than 1 million barrels of oil equivalent a year or holding more than 25 million.
"""

from __future__ import annotations

import csv
from collections import Counter

from ..core.source import Source, SourceInfo

URL = "https://greeninfo-network.github.io/global-oil-gas-extraction-tracker/data/data.csv"
FILE = "goget_map_data.csv"


class GemOilGas(Source):
    info = SourceInfo(
        id="gem_oil_gas",
        title="Global Oil and Gas Extraction Tracker (India)",
        publisher="Global Energy Monitor",
        homepage="https://globalenergymonitor.org/projects/global-oil-gas-extraction-tracker/",
        license="CC BY 4.0",
        description="Oil and gas extraction blocks and fields in India from GEM's Global Oil and Gas Extraction "
        "Tracker, with status, operator and location, from the data file behind GEM's public map.",
        used_for=["Oil and gas resources"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force)

    def process(self):
        with open(self.raw_dir / FILE, encoding="utf-8", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["country"] == "India"]
        where = Counter((r["lat"], r["lng"]) for r in rows)
        out = []
        for r in rows:
            placeholder = where[(r["lat"], r["lng"])] >= 3  # GOGET's country-centre point for "location unknown"
            try:
                lat, lon = float(r["lat"]), float(r["lng"])
            except ValueError:
                lat = lon = None
            out.append({"name": r["project"], "status": r["status"], "fuel": r["fuel_type"], "unit": r["unit_type"],
                        "operator": r["operator"] or None, "start": r["start_year"] or None,
                        "discovered": r["discovery_year"] or None,
                        "lat": None if placeholder else lat, "lon": None if placeholder else lon,
                        "url": r["url"] or None})
        placed = sum(1 for r in out if r["lat"] is not None)
        print(f"    {len(out)} Indian oil and gas assets, {placed} with a location")
        return {"vintage": "GOGET map data (August 2023)", "_files": [FILE], "assets": out}
