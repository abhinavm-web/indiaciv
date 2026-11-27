"""World Heritage sites, national parks and universities in India, queried from Wikidata at build time.

The Wikidata Query Service limits clients (at the time of writing, to one request a minute during an outage), so the
queries run one after another with a pause, and each answer is cached like any download. A query that still fails is
reported and its category stays empty and marked pending, so nothing is filled in by hand.
"""

from __future__ import annotations

import json
import time
import urllib.parse

from ..core import fetch as core_fetch
from ..core.source import Source, SourceInfo

WDQS = "https://query.wikidata.org/sparql"
PAUSE_S = 65
HEADERS = {"Accept": "application/sparql-results+json"}

QUERIES = {
    # UNESCO World Heritage designation (P1435 = Q9259), with the inscription date where present.
    "whs": """SELECT ?item ?itemLabel ?coord ?year WHERE {
  ?item p:P1435 ?st . ?st ps:P1435 wd:Q9259 . OPTIONAL { ?st pq:P580 ?start . BIND(YEAR(?start) AS ?year) }
  ?item wdt:P17 wd:Q668 ; wdt:P625 ?coord .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }""",
    # National parks of India (instance of Q46169) with coordinates; area in hectares where given.
    "parks": """SELECT ?item ?itemLabel ?coord (MAX(?a) AS ?area) WHERE {
  ?item wdt:P31/wdt:P279* wd:Q46169 ; wdt:P17 wd:Q668 ; wdt:P625 ?coord .
  OPTIONAL { ?item p:P2046 ?ap . ?ap psv:P2046 [ wikibase:quantityAmount ?av ; wikibase:quantityUnit ?u ] .
             BIND(IF(?u = wd:Q35852, ?av, IF(?u = wd:Q712226, ?av * 100, ?av)) AS ?a) }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } } GROUP BY ?item ?itemLabel ?coord""",
    # Capitals: of India (Q668) and of each state / UT (items with an ISO 3166-2:IN code), with coordinates.
    "capitals": """SELECT ?of ?iso ?cap ?capLabel ?coord WHERE {
  { BIND(wd:Q668 AS ?of) BIND("IN" AS ?iso) ?of wdt:P36 ?cap . }
  UNION { ?of wdt:P300 ?iso . FILTER(STRSTARTS(?iso, "IN-")) ?of wdt:P36 ?cap . }
  ?cap wdt:P625 ?coord .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }""",
    # Universities in India with coordinates and their number of Wikipedia editions (a prominence signal).
    "universities": """SELECT ?item ?itemLabel ?coord ?links WHERE {
  ?item wdt:P31/wdt:P279* wd:Q3918 ; wdt:P17 wd:Q668 ; wdt:P625 ?coord ; wikibase:sitelinks ?links .
  FILTER(?links >= 8)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }""",
}


def _point(wkt: str):
    # "Point(lon lat)"
    lon, lat = wkt[wkt.index("(") + 1: wkt.index(")")].split()
    return float(lon), float(lat)


class WikidataSites(Source):
    info = SourceInfo(
        id="wikidata_sites",
        title="World Heritage sites, national parks and universities in India via Wikidata",
        publisher="Wikidata (UNESCO, Ministry of Environment, Forest and Climate Change, and others)",
        homepage="https://www.wikidata.org/",
        license="CC0 (Wikidata)",
        description="Items in India with the World Heritage Site designation and inscription year; national parks "
        "with coordinates and area; universities with coordinates and Wikipedia articles in at least 8 languages. "
        "Queried from the Wikidata Query Service at build time.",
        used_for=["Wonders (World Heritage, national parks, universities)", "Culture and Science yields",
                  "National and state capitals"],
    )

    def fetch(self, force=False):
        first = True
        for key, q in QUERIES.items():
            rel = f"{key}.json"
            if (self.raw_dir / rel).exists() and not force:
                continue
            if core_fetch.OFFLINE:
                raise core_fetch.OfflineError(f"--offline: {self.id}/{rel} is not cached")
            if not first:
                time.sleep(PAUSE_S)
            first = False
            url = f"{WDQS}?format=json&query={urllib.parse.quote(q)}"
            for attempt in range(3):
                try:
                    self.download(url, rel, force=force, headers=HEADERS)
                    break
                except Exception as exc:  # 429 under the outage limit: wait and try again
                    print(f"      {key}: {exc}; waiting {PAUSE_S}s")
                    time.sleep(PAUSE_S)
            else:
                print(f"    {key}: not fetched; this category stays pending")

    def _rows(self, key):
        p = self.raw_dir / f"{key}.json"
        if not p.exists():
            return None
        out = []
        for b in json.loads(p.read_text(encoding="utf-8"))["results"]["bindings"]:
            lon, lat = _point(b["coord"]["value"])
            item = "item" if "item" in b else "cap"
            out.append({"qid": b[item]["value"].rsplit("/", 1)[-1], "name": b[f"{item}Label"]["value"],
                        "lon": lon, "lat": lat, **{k: b[k]["value"].rsplit("/", 1)[-1] for k in b
                                                   if k not in ("item", "itemLabel", "coord")}})
        return out

    def process(self):
        out, pending, files = {}, [], []
        for key in [k for k in QUERIES if k != "capitals"]:
            rows = self._rows(key)
            if rows is None:
                pending.append(key)
                out[key] = []
                continue
            files.append(f"{key}.json")
            seen = {}
            for r in rows:  # one row per item (several coordinates or start dates: keep the first / earliest)
                prev = seen.get(r["qid"])
                if prev is None or (key == "whs" and r.get("year") and (not prev.get("year") or
                                                                         int(r["year"]) < int(prev["year"]))):
                    seen[r["qid"]] = r
            out[key] = list(seen.values())
        for r in out["whs"]:
            r["year"] = int(r["year"]) if r.get("year") else None
        for r in out["parks"]:
            r["area_ha"] = float(r.pop("area")) if r.get("area") else None
        caps = {}
        for r in self._rows("capitals") or []:
            caps.setdefault(r["iso"], []).append({"qid": r["qid"], "name": r.get("capLabel", r["name"]),
                                                   "lon": r["lon"], "lat": r["lat"]})
        out["capitals"] = caps
        for r in out["universities"]:
            r["sitelinks"] = int(r.pop("links"))
        if not (self.raw_dir / "capitals.json").exists():
            pending.append("capitals")
        else:
            files.append("capitals.json")
        print(f"    {len(out['capitals'])} capitals, {len(out['whs'])} World Heritage items, {len(out['parks'])} national parks, "
              f"{len(out['universities'])} universities; pending: {pending or 'none'}")
        return {"vintage": "Wikidata (queried at build)", "_files": files, "pending": pending, **out}
