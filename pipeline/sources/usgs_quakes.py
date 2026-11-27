"""Earthquakes of magnitude 5.5 or more since 1900 around India, from the USGS comprehensive catalogue (ComCat)."""

from __future__ import annotations

import csv
import urllib.parse

from ..core.region import BBOX
from ..core.source import Source, SourceInfo

MIN_MAG = 5.5
START = "1900-01-01"
FILE = "quakes_m55_since1900.csv"


def _url():
    lon0, lat0, lon1, lat1 = BBOX
    q = {"format": "csv", "starttime": START, "minmagnitude": MIN_MAG, "minlatitude": lat0, "maxlatitude": lat1,
         "minlongitude": lon0, "maxlongitude": lon1, "orderby": "time-asc"}
    return "https://earthquake.usgs.gov/fdsnws/event/1/query?" + urllib.parse.urlencode(q)


class UsgsQuakes(Source):
    info = SourceInfo(
        id="usgs_quakes",
        title="Earthquakes of magnitude 5.5 or more since 1900",
        publisher="U.S. Geological Survey (ComCat)",
        homepage="https://earthquake.usgs.gov/earthquakes/search/",
        license="Public domain",
        description=f"Every earthquake of magnitude {MIN_MAG} or more in the USGS comprehensive catalogue since "
        "1900, in the map window around India, queried from the USGS event web service at build time.",
        used_for=["Earthquakes lens"],
    )

    def fetch(self, force=False):
        self.download(_url(), FILE, force=force)

    def process(self):
        out = []
        with open(self.raw_dir / FILE, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                try:
                    out.append({"lon": float(r["longitude"]), "lat": float(r["latitude"]), "mag": float(r["mag"]),
                                "year": int(r["time"][:4])})
                except (KeyError, ValueError):
                    continue
        last = max((q["year"] for q in out), default=None)
        print(f"    {len(out)} earthquakes M{MIN_MAG}+ ({START[:4]} to {last})")
        return {"vintage": f"USGS ComCat, M{MIN_MAG}+ since {START[:4]} (retrieved at build)", "_files": [FILE],
                "quakes": out}
