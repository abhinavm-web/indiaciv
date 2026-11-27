"""GeoNames populated places in India: coordinates for census towns and urban agglomerations.

The census tables have no coordinates. GeoNames' India extract gives every populated place (feature class P) with a
point, its names and alternate names. The cities builder matches each census city to a GeoNames place by name, and
accepts the match only if the point lies inside the city's own 2011 sub-district or district outline.
"""

from __future__ import annotations

import io
import zipfile

from ..core.source import Source, SourceInfo

URL = "https://download.geonames.org/export/dump/IN.zip"
FILE = "IN.zip"


class GeoNames(Source):
    info = SourceInfo(
        id="geonames",
        title="GeoNames gazetteer: India (populated places)",
        publisher="GeoNames (geonames.org)",
        homepage="https://www.geonames.org/countries/IN/",
        license="CC BY 4.0",
        description="Names, alternate names and coordinates of populated places in India. Used only to place census "
        "cities on the map; a match must fall inside the city's own census sub-district or district.",
        used_for=["City locations"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        places = []
        with zipfile.ZipFile(self.raw_dir / FILE) as z:
            with z.open("IN.txt") as f:
                for line in io.TextIOWrapper(f, encoding="utf-8"):
                    p = line.rstrip("\n").split("\t")
                    if len(p) < 15 or p[6] != "P":
                        continue
                    alts = [a for a in p[3].split(",") if a and a.isascii()] if p[3] else []
                    places.append({"id": int(p[0]), "name": p[1], "ascii": p[2], "alt": alts[:25],
                                   "lat": float(p[4]), "lon": float(p[5]), "code": p[7],
                                   "pop": int(p[14] or 0)})
        print(f"    {len(places):,} populated places")
        return {"vintage": "GeoNames India extract (retrieved at build)", "_files": [FILE], "places": places}
