"""Cities, states (states.json), districts (counties.json) and the nation: population, yields, GDP and ranks.

Population is the 2011 census (the latest published), on today's districts and states (see population.py). Gold is
state GDP (RBI handbook, 2022-23); India publishes no comparable district or city GDP, so those are null ("Pending"),
not population-split estimates. Food is the census count of farm workers, Production power-plant capacity, Science
prominent universities and Culture World Heritage properties (see yields.py).

Cities are the 2011 census urban agglomerations and the towns outside them, with 100,000 people or more. The census has
no coordinates, so each is matched to a GeoNames populated place of the same name whose point lies in one of today's
districts that the city's own 2011 district (or, failing that, state) became. Census towns with an acronym for a name (GVMC)
take the largest GeoNames place inside their own sub-districts. A city with no match is left out and listed as
pending. Capitals are Wikidata's (P36), matched to the nearest placed city. A city's footprint is its district's hexes when it is the district's largest city (the closest
match to a US metro area), otherwise its own hex.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict

from ..core.geo import MapProjection, Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.region import CAPITAL
from ..core.store import load_interim, save_interim, write_web
from .labels import label_anchor
from .yields import HEX_AREA_KM2, YIELD_KEYS, YIELDS

REQUIRES = ["_world", "_population", "india_boundaries", "census2011", "rbi_states", "geonames", "wikidata_sites",
            "wri_power_plants"]
PRODUCES = ["cities.json", "states.json", "nation.json", "counties.json", "_economy", "_pending"]

POP_YEAR = 2011
GDP_YEAR = "2022-23"
LAKH = 1e5
MIN_CITY_POP = 100_000
PEERS = 5
PCT_KEYS = ["forest", "crop", "pasture", "grass", "shrub", "wetland", "developed"]
EXCLUDED_FUELS = {"Nuclear"}
WHS_MERGE_KM = 40.0
FARM = ["MAIN_CL_P", "MAIN_AL_P", "MARG_CL_P", "MARG_AL_P"]


def ring_search(grid, start, max_rings):
    seen, frontier = {start}, [start]
    yield start
    for _ in range(max_rings):
        nxt = []
        for c in frontier:
            for nb in grid.neighbours(c):
                if nb not in seen:
                    seen.add(nb)
                    nxt.append(nb)
                    yield nb
        frontier = nxt


def land_cell(grid, owner, x, y, taken=None, max_rings=6):
    c = grid.cell_at(x, y)
    if c < 0:
        return -1
    for k in ring_search(grid, c, max_rings):
        if owner[k] >= 0 and (taken is None or k not in taken):
            return k
    return -1


def shoelace_km2(rings, proj):
    total = 0.0
    for ring in rings:
        pts = [proj(lon, lat) for lon, lat in ring]
        total += sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])) / 2
    return abs(total)


def whs_properties(whs):
    """Group World Heritage items that are parts of one property: same inscription year, within WHS_MERGE_KM."""
    groups = []
    for s in sorted(whs, key=lambda s: (s.get("year") or 9999, s["name"])):
        for g in groups:
            if g[0].get("year") == s.get("year") and s.get("year") and any(
                    math.dist((s["lon"], s["lat"]), (o["lon"], o["lat"])) * 111 < WHS_MERGE_KM for o in g):
                g.append(s)
                break
        else:
            groups.append([s])
    return groups


def farm(rec):
    vals = [rec.get(c) for c in FARM]
    return sum(v for v in vals if v is not None) if any(v is not None for v in vals) else None


def ratio(a, b, nd=4):
    return round(a / b, nd) if a is not None and b else None


def literacy(rec):
    p, p6, lit = rec.get("TOT_P"), rec.get("P_06"), rec.get("P_LIT")
    return ratio(lit, p - p6) if None not in (p, p6, lit) and p > p6 else None


SUFFIX = re.compile(r"\s*\((?:[^)]*)\)\s*|\s+UA$|\s+U\.A\.$|\+OG|\s+Part$", re.I)


def clean_city(name: str) -> str:
    n = re.sub(r"^\s*\(\w+\)\s*", "", name)  # "(a) ", "(i) " list markers
    n = SUFFIX.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip(" -")


def edit_distance(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("india_boundaries")
    popd = load_interim("_population")
    census = load_interim("census2011")
    rbi = load_interim("rbi_states")["tables"]
    places = load_interim("geonames")["places"]
    sites = load_interim("wikidata_sites")
    plants = load_interim("wri_power_plants")["plants"]
    proj, grid = MapProjection(**world["projection"]), HexGrid(**world["grid"])
    owner, cover, pct = world["owner"], world["cover"], world["pct"]
    cell_county = world.get("county") or [max(set(s), key=s.count) if s else -1 for s in world["county_samples"]]
    geoids = world["counties"]
    gindex = {g: k for k, g in enumerate(geoids)}
    cmeta = {c["geoid"]: c for c in bounds["counties"]}
    pending = defaultdict(list)

    # ---- per-cell point yields (Production, Science, Culture) -----------------------------------------------------
    n = grid.size
    cell_y = {k: [0.0] * n for k in ("production", "science", "culture")}

    def put(key, lon, lat, v=1.0):
        if lon is None or lat is None:
            return None
        c = land_cell(grid, owner, *proj(lon, lat), max_rings=2)
        if c >= 0:
            cell_y[key][c] += v
        return c

    for p in plants:
        if p["fuel"] not in EXCLUDED_FUELS and p["mw"]:
            put("production", p["lon"], p["lat"], p["mw"])
    for u in sites["universities"]:
        put("science", u["lon"], u["lat"])
    whs_groups = whs_properties(sites["whs"])
    for g in whs_groups:
        put("culture", g[0]["lon"], g[0]["lat"])
    for cat in sites.get("pending", []):
        pending["sources"].append({"what": f"Wikidata {cat}", "why": "query did not return (rate limit)"})

    def sum_cells(cells):
        return {k: round(sum(cell_y[k][c] for c in cells), 1) for k in cell_y}

    # ---- districts --------------------------------------------------------------------------------------------------
    cells_of_county = defaultdict(list)
    for i, k in enumerate(cell_county):
        if k is not None and k >= 0 and owner[i] >= 0:
            cells_of_county[k].append(i)
    fips_index = {f: i for i, f in enumerate(world["states"])}
    smeta = {s["fips"]: s for s in bounds["states"]}
    county_rows = []
    for k, g in enumerate(geoids):
        m = cmeta[g]
        d = popd["districts"][g]
        tot, urb = d["total"], d["urban"]
        name = popd["name_fix"].get(g, m["name"])
        area = shoelace_km2(m["rings"], proj)
        pop = tot.get("TOT_P")
        cells = cells_of_county[k]
        land_cells = [c for c in cells if cover[c]]
        if not pop:
            pending["districts"].append({"geoid": g, "name": name, "state": smeta[m["state_fips"]]["name"],
                                         "why": "no 2011 census area (created later from straddling sub-districts, "
                                         "or not enumerated)"})
        rep = None
        if not cells:
            xs = [proj(lon, lat) for ring in m["rings"] for lon, lat in ring]
            if xs:
                rep = land_cell(grid, owner, sum(x for x, _ in xs) / len(xs), sum(y for _, y in xs) / len(xs))
        county_rows.append({
            "geoid": g, "name": name, "state": smeta[m["state_fips"]]["abbr"], "si": fips_index[m["state_fips"]],
            "population": pop, "households": tot.get("No_HH"), "land_km2": round(area, 1),
            "density": round(pop / area, 1) if pop and area else None,
            "urban": ratio(urb.get("TOT_P"), pop), "literacy": literacy(tot),
            "workers": tot.get("TOT_WORK_P"), "farm_workers": farm(tot),
            "farm_share": ratio(farm(tot), tot.get("TOT_WORK_P")),
            "parent_2011": (d.get("parent_2011") or {}).get("name"),
            "gdp": None,
            "land": {kk: (round(sum(pct[kk][c] for c in land_cells) / len(land_cells) / 100, 4) if land_cells else None)
                     for kk in PCT_KEYS},
            "cells": cells, "cell": cells[len(cells) // 2] if cells else rep,
            "yields": {**sum_cells(cells), "food": farm(tot), "gold": None},
        })

    # ---- states -----------------------------------------------------------------------------------------------------
    by_state = defaultdict(list)
    for r in county_rows:
        by_state[r["si"]].append(r)
    gsdp = rbi["gsdp"]
    states = []
    cells_of_state = defaultdict(list)
    for i, o in enumerate(owner):
        if o >= 0:
            cells_of_state[o].append(i)
    for si, fips in enumerate(world["states"]):
        m = smeta[fips]
        rows = by_state[si]
        tot = defaultdict(int)
        urb = 0
        for g in (r["geoid"] for r in rows):
            for c, v in popd["districts"][g]["total"].items():
                tot[c] += v
            urb += popd["districts"][g]["urban"].get("TOT_P") or 0
        pop = tot.get("TOT_P") or None
        v = (gsdp.get(fips) or {}).get(GDP_YEAR)
        gdp = round(v * LAKH) if v else None
        if gdp is None:
            pending["state_gdp"].append({"state": m["name"], "why": f"no {GDP_YEAR} GSDP in the RBI handbook"})
        pc = (rbi["nsdp_per_capita"].get(fips) or {}).get(GDP_YEAR)
        sectors = {key.removeprefix("gsva_"): round(t[fips][GDP_YEAR] * LAKH)
                   for key, t in rbi.items() if key.startswith("gsva_") and (t.get(fips) or {}).get(GDP_YEAR)}
        cells = cells_of_state[si]
        land_cells = [c for c in cells if cover[c]]
        ys = sum_cells(cells)
        states.append({
            "fips": fips, "abbr": m["abbr"], "iso": m["iso"], "name": m["name"], "wikidata": None,
            "population": pop, "employed": tot.get("TOT_WORK_P"),
            "yields": {**ys, "food": farm(tot), "gold": gdp},
            "jobs": {}, "median_income": None, "median_rent": None, "home_value": None,
            "unemployment": None, "rent_burden": None,
            "gdp": gdp, "gdp_year": GDP_YEAR, "gdp_by_sector": sectors or None,
            "nsdp_per_capita": pc, "gdp_series": {y: round(x * LAKH) for y, x in sorted((gsdp.get(fips) or {}).items())
                                                   if x is not None},
            "urban": ratio(urb, pop), "literacy": literacy(tot), "households": tot.get("No_HH"),
            "growth": None, "growth_years": None, "pop_series": {str(POP_YEAR): pop} if pop else {},
            "ranks": {},
            "label": label_anchor(grid, owner, si, m["name"]),
            "land": ({k: round(sum(pct[k][c] for c in land_cells) / len(land_cells) / 100, 3) for k in PCT_KEYS}
                     if land_cells else None),
            "energy": None,
            "land_km2": round(sum(r["land_km2"] for r in rows)),
            "districts": len(rows),
        })

    # ---- cities -----------------------------------------------------------------------------------------------------
    # Where did each 2011 district / state go? (sets of today's district indices)
    went_dt, went_st = defaultdict(set), defaultdict(set)
    for key, g in popd["subdistrict_district"].items():
        went_dt[key[:5]].add(gindex[g])
        went_st[key[:2]].add(gindex[g])
    county_idx = ShapeIndex([Shape([[proj(lon, lat) for lon, lat in r] for r in cmeta[g]["rings"]]) for g in geoids],
                            cell_km=60)
    # 2011 sub-district outlines by census key (same matching as population.py)
    subs = bounds["subdistricts"]
    by_dt_sdt = {f"{b['dt']}{b['sdt']}": k for k, b in enumerate(subs)}
    by_sdt = defaultdict(list)
    for k, b in enumerate(subs):
        by_sdt[b["sdt"]].append(k)
    sub_shape = {}

    def outline(key):
        k = by_dt_sdt.get(key[2:])
        if k is None and key[5:] != "99999" and len(by_sdt.get(key[5:], [])) == 1:
            k = by_sdt[key[5:]][0]
        if k is None:
            return None
        if k not in sub_shape:
            sub_shape[k] = Shape([[proj(lon, lat) for lon, lat in r] for r in subs[k]["rings"]])
        return sub_shape[k]

    by_name = defaultdict(list)
    for p in places:
        for nm in {p["name"], p["ascii"], *p["alt"]}:
            by_name[norm(nm)].append(p)
    rank_code = {"PPLC": 0, "PPLA": 1, "PPLA2": 2, "PPLA3": 3, "PPL": 4}

    # coarse spatial buckets of places, to find the ones near a city's sub-districts quickly
    bucket = defaultdict(list)
    for p in places:
        bucket[(round(p["lon"] * 2), round(p["lat"] * 2))].append(p)

    def near(shapes):
        xs = [pt for sh in shapes for ring in sh.rings for pt in ring]
        lons_lats = [proj.inverse(x, y) for x, y in xs[:: max(1, len(xs) // 200)]]
        keys = {(round(lo * 2) + dx, round(la * 2) + dy) for lo, la in lons_lats for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)}
        return [p for k in keys for p in bucket.get(k, [])]

    def inside(p, shapes):
        x, y = proj(p["lon"], p["lat"])
        return any(sh.contains(x, y) for sh in shapes)

    def locate(c):
        """(place, how): a GeoNames place of the city's name in its own 2011 sub-districts, else in today's
        districts its 2011 area became; for acronym names (GVMC), the largest place in its own sub-districts."""
        shapes = [sh for sh in (outline(k) for k in c["sub_keys"]) if sh]
        for test, how in ((lambda p: shapes and inside(p, shapes), "name in its sub-district"),
                          (lambda p: county_idx.locate(*proj(p["lon"], p["lat"])) in c["allowed"],
                           "name in its district")):
            best = None
            for nm in c["names"]:
                for p in by_name.get(norm(nm), []):
                    if test(p):
                        key = (rank_code.get(p["code"], 5), -p["pop"])
                        if best is None or key < best[0]:
                            best = (key, p)
                if best:
                    return best[1], how
        if not shapes:
            return None, None
        local = [p for p in near(shapes) if inside(p, shapes)]
        # Spelling variants (Raurkela / Rourkela, Bulandshahar / Bulandshahr) and the first name of a compound
        # (Nanded Waghala, Farrukhabad-cum-Fatehgarh): only among places inside the city's own sub-districts.
        targets = {norm(nm) for nm in c["names"]}
        targets |= {norm(re.split(r"[\s-]+", nm)[0]) for nm in c["names"] if len(re.split(r"[\s-]+", nm)[0]) >= 5}
        best = None
        for p in local:
            for nm in {p["name"], p["ascii"], *p["alt"]}:
                a = norm(nm)
                if len(a) >= 5 and any(t == a or (len(t) >= 6 and edit_distance(a, t) <= 2) for t in targets):
                    key = (rank_code.get(p["code"], 5), -p["pop"])
                    if best is None or key < best[0]:
                        best = (key, p)
        if best:
            return best[1], "similar name in its sub-district"
        if re.fullmatch(r"[A-Z]{2,6}", c["names"][0]):  # an acronym (GVMC): the main seat in its sub-districts
            cands = [p for p in local if p["pop"] >= 0.5 * (c["rec"]["TOT_P"] or 0) and p["code"] in rank_code]
            if cands:
                return min(cands, key=lambda p: (rank_code[p["code"]], -p["pop"])), "largest place in its sub-district"
        return None, None

    in_ua = set()
    raw = []
    uas = census["uas"]
    for u in uas:
        if u["level"] and u["town"]:
            in_ua.add(u["town"])
    for k, u in enumerate(uas):
        if u["level"] != 0 or (u["TOT_P"] or 0) < MIN_CITY_POP:
            continue
        parts = []
        for v in uas[k + 1:]:
            if v["level"] == 0:
                break
            parts.append(v)
        dts = {f"{v['st']}{v['dt']}" for v in parts if v["dt"] and v["dt"] != "000"}
        allowed = set().union(*(went_dt[d] for d in dts)) if dts else set()
        if not dts or any(v["dt"] == "000" for v in parts if v["level"] == 1):
            allowed |= went_st[u["st"]]  # a constituent spans districts (Greater Mumbai): its 2011 state
        sub_keys = sorted({f"{v['st']}{v['dt']}{v['sdt']}" for v in parts if v["sdt"] and v["sdt"] != "00000"})
        main = max((v for v in parts if v["town"]), key=lambda v: v["TOT_P"] or 0, default=None)
        name = clean_city(u["name"])
        short = re.sub(r"^(Greater|Bruhat)\s+", "", name)
        names = [short, name] + ([clean_city(main["name"])] if main else [])
        raw.append({"id": f"UA{u['st']}-{u['ua']}", "name": short, "census_name": u["name"], "kind": "urban agglomeration",
                    "rec": u, "names": names, "allowed": allowed, "sub_keys": sub_keys})
    towns = {}
    for t in census["towns"]:  # a town split across sub-districts comes as several "(Part)" rows: add them up
        if t["town"] in in_ua:
            continue
        agg = towns.setdefault(t["town"], {"town": t["town"], "st": t["st"], "dt": t["dt"], "name": t["name"],
                                           "keys": set(), **{c: 0 for c in census["columns"]}})
        agg["keys"].add(f"{t['st']}{t['dt']}{t['sdt']}")
        for c in census["columns"]:
            agg[c] += t.get(c) or 0
    for t in towns.values():
        if t["TOT_P"] < MIN_CITY_POP:
            continue
        keys = sorted(t["keys"])
        allowed = {gindex[g] for g in (popd["subdistrict_district"].get(k) for k in keys) if g}
        allowed |= set().union(*(went_dt[k[:5]] for k in keys))
        raw.append({"id": f"T{t['town']}", "name": clean_city(t["name"]), "census_name": t["name"], "kind": "town",
                    "rec": t, "names": [clean_city(t["name"])], "allowed": allowed or went_st[t["st"]],
                    "sub_keys": keys})

    raw.sort(key=lambda c: -(c["rec"]["TOT_P"] or 0))
    taken = set()
    cities = []
    county_owner = {}
    for c in raw:
        p, how = locate(c)
        if p is None:
            pending["cities"].append({"name": c["name"], "census_name": c["census_name"],
                                      "population": c["rec"]["TOT_P"],
                                      "why": "no GeoNames place of that name inside its census sub-district or "
                                             "district"})
            continue
        if how == "largest place in its sub-district":
            c["name"] = p["name"]
        x, y = proj(p["lon"], p["lat"])
        cell = land_cell(grid, owner, x, y)
        if cell < 0:
            pending["cities"].append({"name": c["name"], "census_name": c["census_name"],
                                      "population": c["rec"]["TOT_P"], "why": "no land hex near its point"})
            continue
        free = land_cell(grid, owner, x, y, taken=taken, max_rings=2)
        if free >= 0:
            cell = free
        taken.add(cell)
        k = county_idx.locate(x, y)
        if k < 0:
            k = cell_county[cell]
        si = fips_index[cmeta[geoids[k]]["state_fips"]] if k >= 0 else owner[cell]
        if k >= 0 and k not in county_owner:
            county_owner[k] = c["id"]
            fp = sorted(set(cells_of_county[k]) | {cell})
        else:
            fp = [cell]
        st = states[si]
        rec = c["rec"]
        ys = sum_cells(fp)
        cities.append({
            "id": c["id"], "name": c["name"], "full": f"{c['name']}, {st['name']}",
            "census_name": c["census_name"], "kind": c["kind"], "located_by": how,
            "states": [st["abbr"]], "metro": rec["TOT_P"] >= 1_000_000,
            "capital": False, "province_capital": False,
            "x": round(x, 1), "y": round(y, 1), "cell": cell, "lon": p["lon"], "lat": p["lat"],
            "population": rec["TOT_P"], "population_year": POP_YEAR, "employed": rec.get("TOT_WORK_P"),
            "households": rec.get("No_HH"), "literacy": literacy(rec),
            "yields": {**ys, "food": farm(rec), "gold": None},
            "jobs": {}, "median_income": None, "median_rent": None, "home_value": None,
            "unemployment": None, "rent_burden": None,
            "gdp": None, "gdp_year": None, "gdp_by_industry": None, "gdp_undisclosed": None, "gdp_estimated": None,
            "growth": None, "growth_years": None,
            "counties": [geoids[k]] if k >= 0 else [],
            "footprint": fp, "pop_series": {str(POP_YEAR): rec["TOT_P"]},
            "ranks": {}, "peers": [],
            "geonames": p["id"], "wikidata": None, "_sub_keys": c["sub_keys"],
        })

    # Capitals (Wikidata P36): the placed city nearest the capital's coordinates, within CAPITAL_KM.
    CAPITAL_KM = 25.0
    iso_state = {s["iso"]: k for k, s in enumerate(states)}
    no_cap = []
    capitals = sites.get("capitals") or {}
    cap_source = "Wikidata P36"
    if not capitals:  # Wikidata did not answer: GeoNames' seats of government (PPLC national, PPLA state)
        cap_source = "GeoNames seats of government (PPLC, PPLA)"
        for p in places:
            if p["code"] not in ("PPLC", "PPLA"):
                continue
            k = county_idx.locate(*proj(p["lon"], p["lat"]))
            if k < 0:
                continue
            iso = "IN" if p["code"] == "PPLC" else smeta[cmeta[geoids[k]]["state_fips"]]["iso"]
            capitals.setdefault(iso, []).append({"qid": None, "name": p["name"], "lon": p["lon"], "lat": p["lat"],
                                                 "pop": p["pop"]})
        for v in capitals.values():
            v.sort(key=lambda c: -c["pop"])
    for iso, caps in sorted(capitals.items()):
        cap = caps[0]
        cx, cy = proj(cap["lon"], cap["lat"])
        pool = cities if iso == "IN" else [c for c in cities if c["states"][0] == states[iso_state[iso]]["abbr"]] \
            if iso in iso_state else []
        def same_place(c):  # the capital's point is in the city's own sub-districts, or the names match
            shapes = [sh for sh in (outline(k) for k in c["_sub_keys"]) if sh]
            a, b = norm(c["name"]), norm(cap["name"])
            return any(sh.contains(cx, cy) for sh in shapes) or a in b or b in a or edit_distance(a, b) <= 2

        pool = [c for c in pool if math.dist((c["x"], c["y"]), (cx, cy)) <= CAPITAL_KM and same_place(c)]
        best = min(pool, key=lambda c: math.dist((c["x"], c["y"]), (cx, cy)), default=None)
        if best:
            if iso == "IN":
                best["capital"] = True
            else:
                best["province_capital"] = True
                best.setdefault("capital_of", []).append(states[iso_state[iso]]["abbr"])
        elif iso in iso_state:
            no_cap.append(f"{states[iso_state[iso]]['name']} ({cap['name']} is not one of the mapped cities of "
                          f"100,000+)")
    for st in states:
        if st["iso"] not in capitals:
            no_cap.append(f"{st['name']} (no capital in {cap_source})")

    # ranks & peers
    rank_keys = ["population", "gdp", "gdp_per_capita", "growth"] + YIELD_KEYS  # gdp and growth: pending (null)

    def value(c, key):
        if key == "gdp_per_capita":
            return c["gdp"] / c["population"] if c["gdp"] and c["population"] else None
        return c["yields"][key] if key in YIELD_KEYS else c[key]

    for key in rank_keys:
        ranked = sorted((c for c in cities if value(c, key) is not None),
                        key=lambda c: (-value(c, key), -c["population"]))
        for r, c in enumerate(ranked, 1):
            c["ranks"][key] = r
        for c in cities:
            c["ranks"].setdefault(key, None)
    for c in cities:
        others = sorted((o for o in cities if o is not c),
                        key=lambda o: abs(math.log(o["population"] / c["population"])))
        c["peers"] = [o["id"] for o in others[:PEERS]]
    for key in YIELD_KEYS:
        ranked = sorted((s for s in states if s["yields"][key] is not None), key=lambda s: -s["yields"][key])
        for r, s in enumerate(ranked, 1):
            s["ranks"][key] = r
        for s in states:
            s["ranks"].setdefault(key, None)
    city_of_county = {geoids[k]: cid for k, cid in county_owner.items()}

    # ---- nation -----------------------------------------------------------------------------------------------------
    nat = census["nation"]["total"]
    with_gdp = [s for s in states if s["gdp"]]
    nat_gdp = sum(s["gdp"] for s in with_gdp)
    nation = {
        "vintage": f"Census {POP_YEAR}", "year": POP_YEAR,
        "gdp_vintage": f"Sum of state GDP {GDP_YEAR} ({len(with_gdp)} of {len(states)} states and UTs; RBI handbook)",
        "nation": {
            "population": nat["TOT_P"], "employed": nat.get("TOT_WORK_P"),
            "yields": {"food": farm(nat), "gold": nat_gdp,
                       **{k: round(sum(s["yields"][k] for s in states), 1) for k in ("production", "science",
                                                                                     "culture")}},
            "jobs": {}, "median_income": None, "median_rent": None, "home_value": None,
            "unemployment": None, "rent_burden": None,
            "gdp": nat_gdp, "gdp_year": GDP_YEAR, "gdp_by_industry": None, "gdp_undisclosed": None,
            "gdp_estimated": None, "growth": None, "growth_years": None,
            "urban": ratio(census["nation"]["urban"]["TOT_P"], nat["TOT_P"]), "literacy": literacy(nat),
        },
        "yields": YIELDS,
        "industries": {},
        "country": "India",
        "currency": "INR",
    }

    # ---- counties.json ----------------------------------------------------------------------------------------------
    fields = [
        ("geoid", "District code", "text", None, "neutral", "india_boundaries",
         "2011 census state code + the boundary file's district code."),
        ("name", "District", "text", None, "neutral", "india_boundaries", "District name."),
        ("state", "State", "text", None, "neutral", "india_boundaries", "ISO 3166-2:IN state code."),
        ("population", "Population", "int", "people", "neutral", "census2011",
         "2011 census, summed over the 2011 sub-districts that lie in today's district."),
        ("households", "Households", "int", "households", "neutral", "census2011", "2011 census."),
        ("land_km2", "Area", "km2", "km²", "neutral", "india_boundaries",
         "Area of the district outline (equal-area projection)."),
        ("density", "Density", "float", "people / km²", "neutral", "census2011", "2011 population ÷ area."),
        ("urban", "Urban", "pct", None, "neutral", "census2011", "Share of the 2011 population in towns."),
        ("literacy", "Literacy", "pct", None, "good", "census2011",
         "Literates ÷ population aged 7 and over (2011 census)."),
        ("workers", "Workers", "int", "people", "neutral", "census2011", "Main and marginal workers, 2011."),
        ("farm_share", "Farm workers", "pct", None, "neutral", "census2011",
         "Cultivators and agricultural labourers ÷ all workers, 2011."),
        ("parent_2011", "2011 district", "text", None, "neutral", "census2011",
         "The 2011 census district that most of today's district's people lived in."),
        ("gdp", "GDP", "inr", "₹", "good", "rbi_states",
         "Pending: India publishes no comparable district GDP series."),
        ("forest", "Forest", "pct", None, "neutral", "worldcover", "Share of land that is tree cover."),
        ("crop", "Cropland", "pct", None, "neutral", "worldcover", "Share of land that is cropland."),
        ("developed", "Built-up", "pct", None, "neutral", "worldcover", "Share of land that is built-up."),
        ("cbsa", "City", "text", None, "neutral", "census2011",
         "The id of the largest city in the district, when it is in cities.json."),
        ("cell", "Map cell", "int", None, "neutral", "india_boundaries", "A representative land hex of the district."),
    ]
    columns = [f[0] for f in fields]
    rows = []
    for r in county_rows:
        rec = {**r, **{k: r["land"][k] for k in ("forest", "crop", "developed")}, "cbsa": city_of_county.get(r["geoid"])}
        rows.append([rec.get(c) for c in columns])
    counties_doc = {
        "vintage": f"Census {POP_YEAR} on today's districts",
        "fields": [{"key": k, "label": lab, "format": fmt, "unit": unit, "higher_is": hi, "source": src,
                    "description": desc} for k, lab, fmt, unit, hi, src, desc in fields],
        "columns": columns, "rows": rows,
    }

    pending["always"] = [
        {"what": "District and city GDP", "why": "no comparable official series is published"},
        {"what": "Population growth", "why": "the 2001 census tables are not yet wired in"},
        {"what": "Population after 2011", "why": "the next census has not published results"},
    ]
    if no_cap:
        pending["state_capitals"] = [{"state": s, "source": cap_source} for s in no_cap]

    for c in cities:
        c.pop("_sub_keys", None)
    nation["pending"] = {k: v for k, v in pending.items()}
    write_web("cities.json", cities)
    write_web("states.json", states)
    write_web("nation.json", nation)
    write_web("counties.json", counties_doc)
    save_interim("_economy", {
        "county_density": [r["density"] for r in county_rows],
        "county_urban": [r["urban"] for r in county_rows],
        "county_literacy": [r["literacy"] for r in county_rows],
        "county_farm_share": [r["farm_share"] for r in county_rows],
        "county_growth": [None for _ in county_rows],
        "cell_county": cell_county,
        "whs": [[s["name"] for s in g] for g in whs_groups],
    })
    save_interim("_pending", dict(pending))
    print(f"    {len(cities)} cities placed, {len(pending['cities'])} pending "
          f"({sum(c['province_capital'] for c in cities)} state capitals), {len(states)} states/UTs "
          f"({len(with_gdp)} with GDP), {len(county_rows)} districts "
          f"({sum(1 for r in county_rows if r['population'])} with population); "
          f"population {nat['TOT_P']:,}; GDP ₹{nat_gdp / 1e12:,.1f} lakh crore; {len(whs_groups)} WHS properties")
