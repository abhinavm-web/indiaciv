"""Coal mines and iron ore mines in India, from Global Energy Monitor's trackers (CC BY 4.0).

The asset list comes from GEM's public asset API (no key needed), one page of up to 500 records at a time. Each
record carries the mine's own coordinates, status, owner and capacity as GEM's researchers recorded them; nothing is
estimated here. Mines without coordinates are kept in the raw file but cannot be placed on the map.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from ..core.fetch import record
from ..core.source import Source, SourceInfo

API = "https://api.globalenergymonitor.org/assets"
META = "https://api.globalenergymonitor.org/catalog/metadata"
KINDS = {"coal-mine": "coal_mines.json", "iron-ore-mine": "iron_ore_mines.json"}
PAGE = 500


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "indiaciv-pipeline", "Accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f > 0 else None


class GemMines(Source):
    info = SourceInfo(
        id="gem_mines",
        title="Global Coal Mine Tracker and Global Iron Ore Mines Tracker (India)",
        publisher="Global Energy Monitor",
        homepage="https://globalenergymonitor.org/projects/global-coal-mine-tracker/",
        license="CC BY 4.0",
        description="Every coal mine and iron ore mine in India in Global Energy Monitor's trackers, with "
        "coordinates, operating status, owner and capacity, read from GEM's public asset API at build time.",
        used_for=["Coal mine and iron ore mine resources", "State mining totals"],
    )

    def fetch(self, force=False):
        for kind, name in KINDS.items():
            path = self.raw_dir / name
            if path.exists() and not force:
                continue
            rows, offset, total = [], 0, None
            while total is None or offset < total:
                q = {"country": "India", "asset_type": kind, "limit": PAGE, "offset": offset,
                     "include_type_fields": "true"}
                d = _get(API + "?" + urllib.parse.urlencode(q))
                total = d["total"]
                rows += d["results"]
                offset += PAGE
                if not d["results"]:
                    break
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"total": total, "results": rows}))
            record(self.id, name, f"{API}?country=India&asset_type={kind}", note="all pages, merged")
        meta = self.raw_dir / "metadata.json"
        if force or not meta.exists():
            meta.write_text(json.dumps(_get(META)))
            record(self.id, "metadata.json", META)

    def process(self):
        cites = {t["slug"]: (t.get("citation") or {}).get("copyright")
                 for t in json.loads((self.raw_dir / "metadata.json").read_text())["trackers"]}
        out = {}
        coal = json.loads((self.raw_dir / KINDS["coal-mine"]).read_text())["results"]
        out["coal"] = []
        for r in coal:
            tf = r.get("type_fields") or {}
            mt = _num(tf.get("capacity_mtpa")) or (_num(r.get("capacity_value")) if r.get("capacity_unit") == "Mtpa"
                                                  else None)
            out["coal"].append({
                "id": r["asset_id"], "name": r["asset_name"], "status": r.get("operating_status"),
                "lon": r.get("longitude"), "lat": r.get("latitude"), "state": r.get("state_province"),
                "tons": round(mt * 1e6) if mt else None, "type": tf.get("mine_type"),
                "coal": tf.get("coal_type"), "coalfield": tf.get("coalfield"), "owner": tf.get("owners"),
                "accuracy": tf.get("location_accuracy"), "opened": tf.get("opening_year")})
        iron = json.loads((self.raw_dir / KINDS["iron-ore-mine"]).read_text())["results"]
        out["iron"] = []
        for r in iron:
            tf = r.get("type_fields") or {}
            kt = _num(tf.get("design_capacity_thousand_tonnes_per_annum"))
            out["iron"].append({
                "id": r["asset_id"], "name": r["asset_name"], "status": r.get("operating_status"),
                "lon": r.get("longitude"), "lat": r.get("latitude"), "state": r.get("state_province"),
                "tons": round(kt * 1e3) if kt else None, "owner": tf.get("owner"),
                "accuracy": tf.get("coordinate_accuracy"), "opened": (tf.get("start_date") or "")[:4] or None})
        for k in ("coal", "iron"):
            n_op = sum(1 for m in out[k] if m["status"] == "operating")
            print(f"    {len(out[k])} {k} mines ({n_op} operating)")
        out["citation"] = {"coal": cites.get("coal-mines"),
                           "iron": "© Global Energy Monitor. Global Iron Ore Mines Tracker. Distributed under a "
                                   "Creative Commons Attribution 4.0 International License."}
        out["vintage"] = (cites.get("coal-mines") or "Global Coal Mine Tracker").split(". ")[1] \
            if cites.get("coal-mines") else "GEM trackers (retrieved at build)"
        out["_files"] = list(KINDS.values()) + ["metadata.json"]
        return out
