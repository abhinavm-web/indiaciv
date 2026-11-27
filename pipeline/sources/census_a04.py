"""Census 2011 table A-04: every town and urban agglomeration, with its population at each census since 1901.

The six tables (size classes I to VI) are found through the Census Digital Library's catalogue search
("PC11_A04") and downloaded from their catalogue pages. Each unit is listed with the population the census counted for
it at every census where it existed, on the unit's boundaries at that census (the table's own footnotes describe the
mergers and extensions). The process step reads them into one list of units; matching them to the map's cities is
done in the economy build, by the 2011 population, which is the same count as the Primary Census Abstract's.
"""

from __future__ import annotations

import json
import re

from ..core import xlsx
from ..core.source import Source, SourceInfo

NADA = "https://censusindia.gov.in/nada/index.php"
SEARCH = f"{NADA}/api/catalog/search?sk=PC11_A04&ps=60"
CLASSES = ["I", "II", "III", "IV", "V", "VI"]


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = re.sub(r"[^\d.]", "", v)
        try:
            return float(s) if s else None
        except ValueError:
            return None
    return None


def _year(v):
    if isinstance(v, (int, float)) and v == int(v) and 1900 <= v <= 2011:
        return int(v)
    if isinstance(v, str) and re.fullmatch(r"[^\w]*((?:19|20)\d\d)[^\w]*", v):  # "!! 2001": a footnote mark
        y = int(re.search(r"(19|20)\d\d", v).group())
        return y if 1900 <= y <= 2011 else None
    return None


def parse(rows):
    """Units in one A-04 table: name, whether it is a top-level unit (numbered) or a constituent, the state written
    under it, and population, area (km²) and civic status by census year."""
    units, cur = [], None
    for r in rows:
        r = list(r) + [None] * 11
        name = r[1].strip() if isinstance(r[1], str) and r[1].strip() else None
        yr = _year(r[3])
        if name and yr and cur is not None and not isinstance(r[0], (int, float)) and \
                not re.match(r"\(\w+\)", name) and yr > max(map(int, cur["pop"] or {"0": 0})):
            cur["name"] = f"{cur['name']} {name}"  # a long name runs on to the next row
        elif name and yr and not name.startswith(("ALL TOWNS", "URBAN AGG")):
            cur = {"name": name, "top": isinstance(r[0], (int, float)), "place": [], "pop": {}, "area": {},
                   "status": {}}
            units.append(cur)
        elif name and not yr:
            cur = None  # a footnote or a heading ends the unit
        if cur is None or not yr:
            continue
        if isinstance(r[2], str) and r[2].strip():
            cur["place"].append(r[2].strip())
        p = _num(r[6])
        if p is not None:
            cur["pop"][str(yr)] = round(p)
        a = _num(r[5])
        if a is not None and a > 0:
            cur["area"][str(yr)] = a
        if isinstance(r[4], str) and r[4].strip():
            cur["status"][str(yr)] = r[4].strip()
    for u in units:
        place = re.sub(r"\s+", " ", " ".join(u["place"]))
        m = re.findall(r"\(([^()]+)\)", place)
        u["state"] = re.sub(r"\s+", " ", m[-1]).strip() if m else None
        u["place"] = place
    return units


class CensusA04(Source):
    info = SourceInfo(
        id="census_a04",
        title="Census 2011 A-04: towns and urban agglomerations with variation since 1901",
        publisher="Office of the Registrar General & Census Commissioner, India (Census Digital Library)",
        homepage=f"{NADA}/catalog/42876",
        license="Government of India open data (attribution: ORGI, Census 2011)",
        description="Population at every census from 1901 to 2011 for each of India's 2011 towns and urban "
        "agglomerations, on each unit's boundaries at that census. Used for city growth from 2001 to 2011.",
        used_for=["City population growth 2001-2011", "City population history"],
    )

    def fetch(self, force=False):
        idx = self.download(SEARCH, "catalog_search.json", force=force)
        rows = json.loads(idx.read_text(encoding="utf-8"))["result"]["rows"]
        tables = {r["idno"].split("-")[-1]: r for r in rows if re.fullmatch(r"PC11_A04-[IV]+", r.get("idno", ""))}
        if set(tables) != set(CLASSES):
            raise SystemExit(f"census_a04: catalogue search found classes {sorted(tables)}, expected {CLASSES}")
        for c, r in tables.items():
            rel = f"A04-{c}.xlsx"
            if (self.raw_dir / rel).exists() and not force:
                continue
            page = self.download(f"{NADA}/catalog/{r['id']}", f"pages/{r['id']}.html", force=force)
            html = page.read_text(encoding="utf-8", errors="ignore")
            links = re.findall(r'href="([^"]+/download/\d+/[^"]+\.xlsx)"', html)
            if not links:
                raise SystemExit(f"census_a04: {r['idno']} has no .xlsx on its catalogue page")
            path = self.download(links[0], rel, force=force)
            if path.read_bytes()[:2] != b"PK":
                self.discard(rel)
                raise SystemExit(f"census_a04: {r['idno']} download is not an Excel file")

    def process(self):
        units, files = [], []
        for c in CLASSES:
            path = self.raw_dir / f"A04-{c}.xlsx"
            files.append(path.name)
            got = parse(xlsx.rows(path))
            for u in got:
                u["class"] = c
            units += got
            print(f"    class {c}: {len(got)} units ({sum(u['top'] for u in got)} top-level)")
        return {"vintage": "Census 2011 (table A-04)", "_files": files, "units": units}
