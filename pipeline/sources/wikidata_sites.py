"""World Heritage sites, national parks and universities in India, queried from Wikidata at build time.

The Wikidata Query Service limits clients (at the time of writing, to one request a minute during an outage), so the
queries run one after another with a pause, and each answer is cached like any download. A query that still fails is
reported and its category stays empty and marked pending, so nothing is filled in by hand.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.error
import urllib.request

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


API = "https://www.wikidata.org/w/api.php"
UA = {"User-Agent": "indiaciv-pipeline/0.1 (https://github.com/abhinavm-web/indiaciv)"}
ISO_CODES = ["AN", "AP", "AR", "AS", "BR", "CH", "CG", "DH", "DL", "GA", "GJ", "HR", "HP", "JK", "JH", "KA", "KL",
             "LA", "LD", "MP", "MH", "MN", "ML", "MZ", "NL", "OD", "PY", "PB", "RJ", "SK", "TN", "TS", "TR", "UP",
             "UK", "WB"]


def _current(claims, prop):
    """Values of a property that are not deprecated and have no end time (P582), preferred rank first."""
    vals = [c for c in claims.get(prop, []) if c.get("rank") != "deprecated" and "P582" not in c.get("qualifiers", {})
            and c["mainsnak"].get("datavalue")]
    vals.sort(key=lambda c: c.get("rank") != "preferred")
    return [c["mainsnak"]["datavalue"]["value"] for c in vals]


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
        if not (self.raw_dir / "capitals.json").exists():
            try:
                self._capitals_api(force)
            except Exception as exc:
                print(f"    capitals via the Wikidata API failed: {exc}")

    def _capitals_api(self, force):
        """Capitals through the Wikidata API (not the query service): each state's item by its ISO 3166-2 code
        (P300), its current capital (P36) and the capital's coordinates (P625)."""
        rel = "capitals_api.json"
        if (self.raw_dir / rel).exists() and not force:
            return
        def get(params):
            q = urllib.parse.urlencode({**params, "format": "json"})
            for attempt in range(6):
                time.sleep(2)
                try:
                    req = urllib.request.Request(f"{API}?{q}", headers=UA)
                    with urllib.request.urlopen(req, timeout=60) as r:
                        return json.loads(r.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    if exc.code != 429:
                        raise
                    time.sleep(int(exc.headers.get("Retry-After") or 10 * (attempt + 1)))
            raise RuntimeError("Wikidata API kept answering 429")
        items = {"IN": "Q668"}
        for code in ISO_CODES:
            hits = get({"action": "query", "list": "search", "srsearch": f"haswbstatement:P300=IN-{code}"})
            res = hits["query"]["search"]
            if len(res) == 1:
                items[f"IN-{code}"] = res[0]["title"]
        ents = {}
        ids = list(items.values())
        for k in range(0, len(ids), 40):
            ents.update(get({"action": "wbgetentities", "ids": "|".join(ids[k:k + 40]), "props": "claims"})["entities"])
        caps = {iso: [v["id"] for v in _current(ents[q]["claims"], "P36")] for iso, q in items.items()}
        cap_ids = sorted({c for v in caps.values() for c in v})
        cents = {}
        for k in range(0, len(cap_ids), 40):
            cents.update(get({"action": "wbgetentities", "ids": "|".join(cap_ids[k:k + 40]),
                              "props": "claims|labels", "languages": "en"})["entities"])
        rows = []
        for iso, cl in caps.items():
            for c in cl:
                pts = _current(cents[c]["claims"], "P625")
                if pts:
                    rows.append({"iso": iso, "of": items[iso], "qid": c, "name":
                                 cents[c].get("labels", {}).get("en", {}).get("value", c),
                                 "lon": pts[0]["longitude"], "lat": pts[0]["latitude"]})
        (self.raw_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.raw_dir / rel).write_text(json.dumps(rows, indent=1), encoding="utf-8")
        core_fetch.record(self.id, rel, API, note="wbsearch haswbstatement:P300, wbgetentities P36 and P625")

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
        api = self.raw_dir / "capitals_api.json"
        if not caps and api.exists():
            for r in json.loads(api.read_text(encoding="utf-8")):
                caps.setdefault(r["iso"], []).append({k: r[k] for k in ("qid", "name", "lon", "lat")})
        out["capitals"] = caps
        for r in out["universities"]:
            r["sitelinks"] = int(r.pop("links"))
        if (self.raw_dir / "capitals.json").exists():
            files.append("capitals.json")
        elif (self.raw_dir / "capitals_api.json").exists():
            files.append("capitals_api.json")
        else:
            pending.append("capitals")
        print(f"    {len(out['capitals'])} capitals, {len(out['whs'])} World Heritage items, {len(out['parks'])} national parks, "
              f"{len(out['universities'])} universities; pending: {pending or 'none'}")
        return {"vintage": "Wikidata (queried at build)", "_files": files, "pending": pending, **out}
