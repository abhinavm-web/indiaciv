"""2011 census counts on today's districts and states.

India has redrawn many districts since 2011 (640 then, about 790 in the boundary file), and split Andhra Pradesh
(Telangana, 2014) and Jammu and Kashmir (Ladakh, 2019). The census only publishes 2011 areas, but its sub-districts
are small and new districts are almost always made of whole sub-districts. So each 2011 sub-district outline is
sampled on a 2 km lattice and given, whole, to the district of today that holds most of its points; its census counts
follow it. Nothing is split or scaled: a district's figure is the sum of real 2011 counts of the sub-districts in it.

Sub-districts that straddle two of today's districts (majority under 90% of points) are counted and reported, with
their population, so the size of the approximation is visible. Census sub-districts with no outline in the boundary
file go to the district of today that most of their 2011 district's other sub-districts went to.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from ..core.geo import MapProjection, Shape, ShapeIndex
from ..core.store import load_interim, save_interim

REQUIRES = ["_world", "india_boundaries", "census2011"]
PRODUCES = ["_population"]

STEP_KM = 2.0
MAX_POINTS = 600
CLEAR_MAJORITY = 0.9


def _lattice(shape: Shape, pts):
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    step = STEP_KM
    while ((x1 - x0) / step + 1) * ((y1 - y0) / step + 1) > MAX_POINTS:
        step *= 1.5
    out = []
    y = y0 + step / 2
    while y < y1:
        x = x0 + step / 2
        while x < x1:
            if shape.contains(x, y):
                out.append((x, y))
            x += step
        y += step
    if not out:  # tiny or thin: fall back to the vertex mean, then to the vertices
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        out = [(cx, cy)] if shape.contains(cx, cy) else pts[:: max(1, len(pts) // 50)]
    return out


def norm_letters(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def _add(acc: dict, rec: dict, cols):
    for c in cols:
        v = rec.get(c)
        if v is not None:
            acc[c] = acc.get(c, 0) + v


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("india_boundaries")
    census = load_interim("census2011")
    proj = MapProjection(**world["projection"])
    cols = census["columns"]
    geoids = world["counties"]
    cmeta = {c["geoid"]: c for c in bounds["counties"]}
    county_shapes = [Shape([[proj(lon, lat) for lon, lat in r] for r in cmeta[g]["rings"]]) for g in geoids]
    county_idx = ShapeIndex(county_shapes, cell_km=60)

    # 1. Each sub-district outline -> today's district (majority of lattice points).
    poly_district, poly_share = [], []
    for s in bounds["subdistricts"]:
        rings = [[proj(lon, lat) for lon, lat in r] for r in s["rings"]]
        pts = _lattice(Shape(rings), [p for r in rings for p in r])
        votes = Counter(k for k in (county_idx.locate(x, y) for x, y in pts) if k >= 0)
        if votes:
            k, n = votes.most_common(1)[0]
            poly_district.append(k)
            poly_share.append(n / sum(votes.values()))
        else:
            poly_district.append(None)
            poly_share.append(0.0)
    by_dt_sdt = {f"{s['dt']}{s['sdt']}": i for i, s in enumerate(bounds["subdistricts"])}
    by_sdt = defaultdict(list)
    for i, s in enumerate(bounds["subdistricts"]):
        by_sdt[s["sdt"]].append(i)

    # 2. Each census sub-district record -> an outline. The outlines carry the 2011 sub-district code, but some
    # carry post-2011 state and district codes, so the 5-digit sub-district code (unique in 2011 except for
    # "(Part)" rows of one sub-district split across districts, and 99999) is the main key.
    assign: dict[str, int] = {}  # census sub-district key -> index into geoids
    how = Counter()
    straddle, straddle_pop = 0, 0
    by_2011_district = defaultdict(Counter)
    pending = []
    for key, rec in census["subdistricts"].items():
        dt, sdt = key[2:5], key[5:]
        i = by_dt_sdt.get(f"{dt}{sdt}")
        if i is None and sdt != "99999" and len(by_sdt.get(sdt, [])) == 1:
            i = by_sdt[sdt][0]
        if i is not None and poly_district[i] is not None:
            assign[key] = poly_district[i]
            how["outline"] += 1
            by_2011_district[key[:5]][poly_district[i]] += 1
            if poly_share[i] < CLEAR_MAJORITY:
                straddle += 1
                straddle_pop += rec.get("total", {}).get("TOT_P") or 0
        else:
            pending.append(key)

    # 3. No outline: the district of today that the 2011 district's other sub-districts went to; failing that
    # (districts with no sub-districts at all, e.g. Mumbai, Kolkata, Chennai, Bengaluru Urban: "Area not under any
    # Sub-district"), today's district of the same name in the same 2011 state.
    def norm(name):
        n = re.sub(r"[^a-z]", "", name.lower().replace("&", "and"))
        for suffix in ("district", "urban", "city"):
            n = n.removesuffix(suffix)
        return n

    names = defaultdict(list)
    for k, g in enumerate(geoids):
        names[norm(cmeta[g]["name"])].append(k)
    no_outline, unplaced = [], []
    for key in pending:
        d = by_2011_district.get(key[:5])
        if d:
            assign[key] = d.most_common(1)[0][0]
            how["2011 district"] += 1
            no_outline.append(key)
            continue
        dname = norm(census["districts"].get(key[:5], {}).get("name", ""))
        cands = names.get(dname, [])
        if len(cands) == 1:
            assign[key] = cands[0]
            how["district name"] += 1
            no_outline.append(key)
        else:
            unplaced.append(key)

    dist = [{"total": {}, "urban": {}, "rural": {}, "subdistricts": 0} for _ in geoids]
    placed_pop = 0
    for key, rec in census["subdistricts"].items():
        k = assign.get(key)
        if k is None:
            continue
        for tru in ("total", "urban", "rural"):
            if tru in rec:
                _add(dist[k][tru], rec[tru], cols)
        dist[k]["subdistricts"] += 1
        placed_pop += rec.get("total", {}).get("TOT_P") or 0
    # Repair truncated district names (see india_boundaries) from the sub-district file's district names.
    sub_dtname = Counter()
    poly_of_key = {}
    for key in assign:
        i = by_dt_sdt.get(f"{key[2:5]}{key[5:]}")
        if i is None and key[5:] != "99999" and len(by_sdt.get(key[5:], [])) == 1:
            i = by_sdt[key[5:]][0]
        if i is not None:
            poly_of_key[key] = i
    dtnames = defaultdict(Counter)
    for key, i in poly_of_key.items():
        dtnames[assign[key]][bounds["subdistricts"][i]["dtname"]] += (
            census["subdistricts"][key].get("total", {}).get("TOT_P") or 0) + 1
    name_fix = {}
    taken = {(cmeta[g]["state_fips"], norm_letters(cmeta[g]["name"])) for g in geoids}
    for k, g in enumerate(geoids):
        if not dtnames[k]:
            continue
        full = dtnames[k].most_common(1)[0][0].strip()
        short = cmeta[g]["name"]
        a, b = norm_letters(short), norm_letters(full)
        if (a and len(b) > len(a) and b.startswith(a) and full[len(short):len(short) + 1].isalpha()
                and (cmeta[g]["state_fips"], b) not in taken):  # never rename onto another district (Kamrup)
            name_fix[g] = full

    # The 2011 district that supplied most of each district's people (its "parent"), for names and context.
    parent = defaultdict(Counter)
    for key, k in assign.items():
        parent[k][key[:5]] += census["subdistricts"][key].get("total", {}).get("TOT_P") or 0
    for k, d in enumerate(dist):
        if parent[k]:
            code, pop = parent[k].most_common(1)[0]
            d["parent_2011"] = {"code": code, "name": census["districts"][code]["name"], "share": round(
                pop / max(1, sum(parent[k].values())), 3)}
    nat = census["nation"]["total"]["TOT_P"]
    unplaced_pop = sum(census["subdistricts"][k].get("total", {}).get("TOT_P") or 0 for k in unplaced)
    empty = [geoids[i] for i, d in enumerate(dist) if not d["subdistricts"]]
    save_interim("_population", {
        "year": 2011,
        "columns": cols,
        "districts": {geoids[i]: d for i, d in enumerate(dist)},
        "subdistrict_district": {k: geoids[v] for k, v in assign.items()},
        "name_fix": name_fix,
        "quality": {
            "census_total": nat, "placed": placed_pop, "unplaced_pop": unplaced_pop,
            "unplaced_subdistricts": unplaced, "no_outline_subdistricts": no_outline, "how": dict(how),
            "straddling_subdistricts": straddle, "straddling_pop": straddle_pop,
            "districts_without_census_area": empty,
        },
    })
    print(f"    {len(assign)} of {len(census['subdistricts'])} census sub-districts placed {dict(how)}; "
          f"unplaced: {[census['subdistricts'][k]['name'] for k in unplaced][:12]}; population placed {placed_pop:,} of {nat:,} "
          f"({placed_pop / nat:.4%}); {straddle} straddle two districts ({straddle_pop:,} people); "
          f"{len(empty)} districts got no sub-district; {len(name_fix)} truncated names repaired")
