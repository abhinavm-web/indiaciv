"""States, districts and 2011 census sub-districts of India.

The outlines follow the official boundary of India (Survey of India): Ladakh and Jammu and Kashmir include the areas
India administers and the areas it claims (Gilgit-Baltistan, Aksai Chin). They come from the INDIAN-SHAPEFILES
project, pinned to one commit so the content cannot change under the same URL.

* States/UTs: 37 outlines with their Local Government Directory (LGD) codes, which are the 2011 census state codes
  (Telangana 36 and Ladakh 37 were added after 2011). Dadra and Nagar Haveli and Daman and Diu were merged into one
  union territory in 2020; their two outlines are merged here into one state with the census code of Dadra and Nagar
  Haveli (26).
* Districts: today's districts (about 790 after the source's inter-state slivers and one non-district island unit are
  dropped), with their state's census code and the source's district code.
* Sub-districts: the 2011 census sub-districts (tehsils / taluks / mandals) with their 2011 census codes. They are not
  drawn; the census builder uses them to move 2011 counts onto today's district borders.
"""

from __future__ import annotations

import json
import math
import re

from ..core.geo import geojson_rings
from ..core.source import Source, SourceInfo

REPO = "datta07/INDIAN-SHAPEFILES"
COMMIT = "08490eaab1b9bb4b55addfb1d2c742586c8d22e0"
BASE = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/INDIA"
FILES = {"states": "INDIA_STATES.geojson", "districts": "INDIA_DISTRICTS.geojson",
         "subdistricts": "INDIAN_SUB_DISTRICTS.geojson"}
SIMPLIFY_DEG = 0.005  # drop ring vertices closer than ~500 m to the previous kept one

# ISO 3166-2:IN subdivision codes, keyed by 2011 census state code (as used by the source's STCODE11).
ISO = {"01": "JK", "02": "HP", "03": "PB", "04": "CH", "05": "UK", "06": "HR", "07": "DL", "08": "RJ", "09": "UP",
       "10": "BR", "11": "SK", "12": "AR", "13": "NL", "14": "MN", "15": "MZ", "16": "TR", "17": "ML", "18": "AS",
       "19": "WB", "20": "JH", "21": "OD", "22": "CG", "23": "MP", "24": "GJ", "26": "DH", "27": "MH",
       "28": "AP", "29": "KA", "30": "GA", "31": "LD", "32": "KL", "33": "TN", "34": "PY", "35": "AN", "36": "TS",
       "37": "LA"}
NAMES = {"26": "Dadra and Nagar Haveli and Daman and Diu", "35": "Andaman and Nicobar Islands",
         "01": "Jammu and Kashmir"}
MERGE = {"25": "26"}  # Daman and Diu -> Dadra and Nagar Haveli and Daman and Diu (merged 26 January 2020)


def _simplify(ring):
    if len(ring) < 8:
        return ring
    out = [ring[0]]
    for p in ring[1:-1]:
        if math.dist(p, out[-1]) >= SIMPLIFY_DEG:
            out.append(p)
    out.append(ring[-1])
    return out if len(out) >= 4 else ring


def _rings(geom):
    return [r for r in (_simplify(r) for r in geojson_rings(geom)) if len(r) >= 4]


# The source lost its diacritics through a legacy font encoding: ">" was ā, "|" and "\\" were ī, "@" and "#" were ū
# (Kolk>ta, Ham|rpur, Dehrad@n, Bengal#ru, B\\dar). They are written back as plain letters.
GLYPHS = str.maketrans({">": "a", "|": "i", "\\": "i", "@": "u", "#": "u", "_": "-"})


def _title(s: str) -> str:
    s = re.sub(r"24\s*parganas", "24 Parganas", s.translate(GLYPHS), flags=re.I)
    small = {"and", "of"}
    words = s.replace("&", "and").split()
    return " ".join(w.lower() if w.lower() in small and k else (w if "(" in w else w.capitalize())
                    for k, w in enumerate(words))


class IndiaBoundaries(Source):
    info = SourceInfo(
        id="india_boundaries",
        title="States, districts and 2011 census sub-districts of India (INDIAN-SHAPEFILES)",
        publisher="INDIAN-SHAPEFILES project (Akula Datta), compiled from official Indian boundary data",
        homepage=f"https://github.com/{REPO}",
        license="MIT",
        description="Outlines of India's states and union territories, today's districts and the 2011 census "
        "sub-districts, drawn on the official boundary of India (Survey of India). Used to decide which state and "
        "district each hex belongs to, and to move 2011 census counts onto today's districts. "
        f"Pinned to commit {COMMIT[:10]}.",
        used_for=["Map: land vs. water", "State borders", "District lookup for lenses and the Explorer",
                  "2011 census counts by today's districts"],
    )

    def fetch(self, force=False):
        for name in FILES.values():
            self.download(f"{BASE}/{name}", f"{COMMIT[:10]}/{name}", force=force)

    def _load(self, key):
        with open(self.raw_dir / f"{COMMIT[:10]}/{FILES[key]}", encoding="utf-8") as f:
            return json.load(f)["features"]

    def process(self):
        merged: dict[str, dict] = {}
        for f in self._load("states"):
            p = f["properties"]
            lgd = f"{int(p['State_LGD']):02d}"  # LGD state code = 2011 census code (STCODE11 is not, for AP and Ladakh)
            code = MERGE.get(lgd, lgd)
            s = merged.setdefault(code, {
                "fips": code, "iso": f"IN-{ISO[code]}", "abbr": ISO[code],
                "name": NAMES.get(code, p["STNAME_SH"].replace("&", "and")),
                "wikidata": None, "rings": []})
            s["rings"] += _rings(f["geometry"])
        states = sorted(merged.values(), key=lambda s: s["name"])

        counties, dropped = [], []
        for f in self._load("districts"):
            p = f["properties"]
            if not p.get("state") or not p.get("district") or p["district"] == "ISLAND":
                dropped.append(p.get("remarks") or p.get("district") or "unnamed")
                continue
            st = "34" if p["state"] == "PUDUCHERRY" else MERGE.get(p["statecode"].zfill(2), p["statecode"].zfill(2))
            if st == "25":
                st = "26"
            counties.append({
                "geoid": f"{st}{p['D_CODE']}", "name": _title(p["district"]), "state_fips": st,
                "code": p.get("dist_code") if p.get("dist_code") not in (None, "NOT AVAILABLE") else None,
                "wikidata": None, "rings": _rings(f["geometry"]),
            })
        # Some districts come as two features with the same LGD district code (e.g. Purba Medinipur): merge them.
        by_code: dict[tuple, dict] = {}
        merged_counties = []
        for c in counties:
            k = (c["state_fips"], c["code"]) if c["code"] else None
            if k and k in by_code:
                by_code[k]["rings"] += c["rings"]
                continue
            if k:
                by_code[k] = c
            merged_counties.append(c)
        counties = sorted(merged_counties, key=lambda c: c["geoid"])
        # The district file cut some names at their first long vowel (Karnataka: "B" for Bagalkote, "Belag" for
        # Belagavi). The population builder repairs a name from the district name the same project gives its
        # sub-districts, when the district name is a strict prefix of it.

        subs = []
        for f in self._load("subdistricts"):
            p = f["properties"]
            rings = _rings(f["geometry"])
            pts = [pt for r in rings for pt in r]
            if not pts:
                continue
            # vertex mean of the outline: only used to decide which of today's districts the sub-district lies in
            subs.append({"st": p["stcode11"], "dt": p["dtcode11"], "sdt": p["sdtcode11"], "name": (p.get("sdtname") or "").translate(GLYPHS),
                         "dtname": (p.get("dtname") or "").translate(GLYPHS),
                         "lon": sum(x for x, _ in pts) / len(pts), "lat": sum(y for _, y in pts) / len(pts),
                         "rings": rings})
        print(f"    {len(states)} states/UTs, {len(counties)} districts ({len(dropped)} non-district units dropped), "
              f"{len(subs)} 2011 sub-districts")
        return {
            "vintage": f"INDIAN-SHAPEFILES @ {COMMIT[:10]}",
            "_files": [f"{COMMIT[:10]}/{n}" for n in FILES.values()],
            "states": states,
            "counties": counties,
            "subdistricts": subs,
            "dropped": dropped,
        }
