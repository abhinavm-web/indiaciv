"""Lenses: one value per hex for the map's colour overlays (see docs/DATA_CONTRACTS.md, lenses.json).

District values are spread to hexes in proportion to how much of each district the hex covers (its 7 samples),
weighted by population for rates. State values (income per person) colour every hex of the state. Earthquakes count USGS
epicentres near each hex. Land lenses come from world.json's WorldCover shares.
"""

from __future__ import annotations

import math
from collections import Counter

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .yields import HEX_AREA_KM2

REQUIRES = ["_world", "_economy", "usgs_quakes", "states.json"]
PRODUCES = ["lenses.json"]

GROUPS = [
    {"id": "people", "name": "People"},
    {"id": "prosperity", "name": "Prosperity"},
    {"id": "health", "name": "Health & housing"},
    {"id": "hazards", "name": "Hazards"},
    {"id": "land", "name": "Land"},
]
QUAKE_RADIUS_KM = 50.0
DOMAIN_NOTE = " Colours span the 2nd–98th percentile of hexes; values beyond are drawn at the end colours."


def nice(v: float, up: bool) -> float:
    if v == 0:
        return 0
    mag = 10 ** (math.floor(math.log10(abs(v))) - 1)
    return round((math.ceil if up else math.floor)(v / mag) * mag, 10)


def percentile_domain(values: list, log: bool) -> list[float] | None:
    vals = sorted(v for v in values if v is not None and (v > 0 or not log))
    if not vals:
        return None
    lo, hi = vals[int(0.02 * (len(vals) - 1))], vals[int(0.98 * (len(vals) - 1))]
    lo, hi = nice(lo, False), nice(hi, True)
    return [lo, hi] if hi > lo else [lo, nice(vals[-1], True)]


LAND_LENSES = {
    "forest": (["forest"], {
        "name": "Forest", "icon": "l-forest", "emoji": "🌲",
        "ramp": ["#0b1f0f", "#14401c", "#1f6b2b", "#3a9443", "#7fc07a", "#d5efcd"],
        "description": "Share of the hex's land covered by trees (ESA WorldCover 2021).",
    }),
    "farmland": (["crop", "pasture"], {
        "name": "Farmland", "icon": "l-farmland", "emoji": "🚜",
        "ramp": ["#141d05", "#2f4510", "#557019", "#84a02a", "#b8cf55", "#eef7b8"],
        "description": "Share of the hex's land that is cropland (ESA WorldCover 2021). WorldCover has no "
        "separate pasture class; grazed steppe counts as grassland.",
    }),
    "developed": (["developed"], {
        "name": "Built-up", "icon": "l-developed", "emoji": "🏙️",
        "ramp": ["#121218", "#2c2c3c", "#4b4b66", "#727294", "#a3a3c2", "#e2e2f0"],
        "description": "Share of the hex's land that is built-up (ESA WorldCover 2021): buildings, roads and "
        "other sealed surfaces.",
    }),
}


def build() -> None:
    import json
    from ..core.paths import WEB_DATA

    world = load_interim("_world")
    eco = load_interim("_economy")
    quakes = load_interim("usgs_quakes")["quakes"]
    states = json.loads((WEB_DATA / "states.json").read_text())
    proj, grid = MapProjection(**world["projection"]), HexGrid(**world["grid"])
    owner, samples = world["owner"], world["county_samples"]
    n = grid.size
    density_c = eco["county_density"]

    def spread(per_county, weight_by_people):
        """District values onto hexes: the mean over the districts the hex covers (its 7 samples), weighted by
        how much of the hex each covers, and for rates also by population density."""
        out = [None] * n
        for i, smp in enumerate(samples):
            if owner[i] < 0 or not smp:
                continue
            parts = Counter(k for k in smp if k is not None and k >= 0)
            vals = [(per_county[k], h * ((density_c[k] or 0) if weight_by_people else 1)) for k, h in parts.items()
                    if per_county[k] is not None]
            w = sum(x for _, x in vals)
            if w:
                out[i] = round(sum(v * x for v, x in vals) / w, 4)
        return out

    density = spread(density_c, False)
    nf = {k: spread(v, True) for k, v in eco.get("county_nfhs", {}).items()}

    def nfhs_lens(key, name, emoji, icon, desc, hi, ramp):
        return {"id": key, "group": "health", "name": name, "icon": icon, "emoji": emoji,
                "unit": "share (NFHS-5, 2019-21)", "format": "pct", "scale": "linear", "ramp": ramp,
                "higher_is": hi, "source": "nfhs5",
                "description": desc + " From the NFHS-5 district fact sheets (2019-21); blank for districts created "
                "after 2017 or without a matching fact sheet.", "values": nf.get(key, [None] * n)}

    GOOD = ["#2a0e05", "#5a240a", "#8f4a14", "#c5862a", "#e8c95a", "#fff1b0"]
    BAD = list(reversed(GOOD))
    health = [
        nfhs_lens("sanitation", "Sanitation", "🚽", "l-home", "Share of people living in households that use an "
                  "improved sanitation facility.", "good", GOOD),
        nfhs_lens("clean_fuel", "Clean cooking fuel", "🔥", "l-home", "Share of households cooking with clean fuel "
                  "(electricity, LPG / natural gas, biogas).", "good", GOOD),
        nfhs_lens("women_schooling", "Women's schooling", "🎓", "l-degrees", "Share of women aged 15-49 with 10 or "
                  "more years of schooling.", "good", GOOD),
        nfhs_lens("insurance", "Health insurance", "🏥", "l-uninsured", "Share of households with any usual member "
                  "covered by a health insurance or financing scheme.", "good", GOOD),
        nfhs_lens("stunting", "Child stunting", "📏", "l-people", "Share of children under 5 who are stunted "
                  "(too short for their age).", "bad", BAD),
        nfhs_lens("child_marriage", "Child marriage", "💍", "l-people", "Share of women aged 20-24 who were married "
                  "before age 18.", "bad", BAD),
    ]
    growth = spread(eco["county_growth"], True)
    urban = spread(eco["county_urban"], True)
    lit = spread(eco["county_literacy"], True)
    farm = spread(eco["county_farm_share"], True)
    pc = [None] * n
    for i, o in enumerate(owner):
        if o >= 0:
            pc[i] = states[o].get("nsdp_per_capita")

    def state_fact(key):
        vals = []
        for o in owner:
            v = None
            if o >= 0:
                for lst in (states[o].get("facts") or {}).values():
                    for f in lst:
                        if f["key"] == key:
                            v = f["value"]
            vals.append(v)
        return vals

    def fact_year(key):
        for st in states:
            for lst in (st.get("facts") or {}).values():
                for f in lst:
                    if f["key"] == key:
                        return f["year"]
        return ""

    # Earthquakes within QUAKE_RADIUS_KM of the hex centre.
    qxy = [(*proj(q["lon"], q["lat"]), q["mag"]) for q in quakes]
    count = [None] * n
    maxmag = [None] * n
    for i in range(n):
        if owner[i] < 0:
            continue
        cx, cy = grid.center(*grid.col_row(i))
        near = [m for x, y, m in qxy if abs(x - cx) <= QUAKE_RADIUS_KM and abs(y - cy) <= QUAKE_RADIUS_KM
                and math.hypot(x - cx, y - cy) <= QUAKE_RADIUS_KM]
        count[i] = len(near)
        maxmag[i] = max(near) if near else None

    lenses = [
        {
            "id": "density", "group": "people", "name": "Population", "icon": "l-people", "emoji": "👥",
            "unit": "people / km²", "format": "int", "scale": "log",
            "ramp": ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"], "higher_is": "neutral",
            "source": "census2011",
            "description": "Residents per km² at the 2011 census: each district's population over its area, "
            "averaged over the districts the hex covers.",
            "values": density,
        },
        {
            "id": "growth", "group": "people", "name": "Growth 2001–2011", "icon": "l-growth", "emoji": "📈",
            "unit": "population change", "format": "pct", "scale": "linear",
            "ramp": ["#8e2a2a", "#c96a4a", "#e8c9a0", "#a9cf8a", "#4f9a4a", "#1f5f2a"], "higher_is": "good",
            "source": "census_a02",
            "description": "Population change from the 2001 to the 2011 census (Table A-02, on 2011 boundaries), per "
            "district. Blank where today's district was carved out of a 2011 district that was split, because the "
            "2001 count for its part is not published.",
            "values": growth,
        },
        {
            "id": "urban", "group": "people", "name": "Urban", "icon": "l-developed", "emoji": "🏙️",
            "unit": "share living in towns", "format": "pct", "scale": "linear",
            "ramp": ["#14201a", "#25403a", "#3a6a63", "#5f9a92", "#9cc9c0", "#e3f4ef"], "higher_is": "neutral",
            "source": "census2011",
            "description": "Share of each district's 2011 population living in statutory or census towns.",
            "values": urban,
        },
        {
            "id": "literacy", "group": "people", "name": "Literacy", "icon": "l-degrees", "emoji": "📚",
            "unit": "literates / people aged 7+", "format": "pct", "scale": "linear",
            "ramp": ["#2a1030", "#55205a", "#7f3f86", "#a86fb0", "#d1a8d6", "#f5e6f7"], "higher_is": "good",
            "source": "census2011",
            "description": "Literates as a share of people aged 7 and over, per district, at the 2011 census.",
            "values": lit,
        },
        {
            "id": "farm", "group": "prosperity", "name": "Farm workers", "icon": "l-farmland", "emoji": "🧑‍🌾",
            "unit": "share of workers", "format": "pct", "scale": "linear",
            "ramp": ["#141d05", "#2f4510", "#557019", "#84a02a", "#b8cf55", "#eef7b8"], "higher_is": "neutral",
            "source": "census2011",
            "description": "Cultivators and agricultural labourers (main and marginal) as a share of all workers, "
            "per district, at the 2011 census.",
            "values": farm,
        },
        {
            "id": "gdp_pc", "group": "prosperity", "name": "Income per person", "icon": "l-income", "emoji": "💵",
            "unit": "₹ per person (2022-23)", "format": "inr", "scale": "linear",
            "ramp": ["#2a1a05", "#5a3a0a", "#8f6414", "#c59a2a", "#e8c95a", "#fff1b0"], "higher_is": "good",
            "source": "rbi_states",
            "description": "Per-capita Net State Domestic Product at current prices, 2022-23 (NSO state accounts, "
            "RBI handbook). Blank for states that have not published it.",
            "note": "State-wide values: every hex of a state has the same colour.",
            "values": pc,
        },
        {
            "id": "poverty", "group": "prosperity", "name": "Poverty", "icon": "l-income", "emoji": "📉",
            "unit": "multidimensionally poor (2019-21)", "format": "pct", "scale": "linear",
            "ramp": ["#fff1b0", "#e8c95a", "#c5862a", "#8f4a14", "#5a240a", "#2a0e05"], "higher_is": "bad",
            "source": "niti_mpi",
            "description": "Share of people who are multidimensionally poor, by district: NITI Aayog's National MPI "
            "(Progress Review 2023), computed from NFHS-5 (2019-21). Blank for districts created after 2017.",
            "values": nf.get("mpi_poor", [None] * n),
        },
        {
            "id": "jobs_ec13", "group": "prosperity", "name": "Business jobs", "icon": "l-income", "emoji": "🏪",
            "unit": "establishment jobs per 100 residents (2013)", "format": "float", "scale": "linear",
            "ramp": ["#2a1a05", "#5a3a0a", "#8f6414", "#c59a2a", "#e8c95a", "#fff1b0"], "higher_is": "good",
            "source": "shrug",
            "description": "Non-farm jobs in establishments at the 2013 Economic Census (MoSPI, via SHRUG) per 100 "
            "people counted in the district at the 2011 census. Includes shops, workshops, offices and public "
            "services; crop farming is not counted.",
            "values": spread(eco.get("county_ec13_per100", [None] * len(density_c)), True),
        },
        {
            "id": "unemployment", "group": "prosperity", "name": "Urban unemployment", "icon": "unemployment",
            "emoji": "😐", "unit": f"urban unemployment rate ({fact_year('unemployment_urban')})", "format": "pct",
            "scale": "linear", "ramp": ["#10241a", "#1f4a33", "#3f7a4f", "#c9a45c", "#d9703a", "#ff5a3a"],
            "higher_is": "bad", "source": "rbi_states",
            "description": "Unemployment rate in towns and cities, usual status (adjusted), from the Periodic Labour "
            "Force Survey as published in the RBI handbook, by state.",
            "note": "State-wide values: every hex of a state has the same colour.",
            "values": state_fact("unemployment_urban"),
        },
        {
            "id": "life", "group": "people", "name": "Life expectancy", "icon": "l-people", "emoji": "❤️",
            "unit": f"years at birth ({fact_year('life_expectancy')})", "format": "float", "scale": "linear",
            "ramp": ["#2a0e14", "#5a1a2a", "#8f2f45", "#c25a6a", "#e89aa0", "#ffe0dc"], "higher_is": "good",
            "source": "rbi_states",
            "description": "Life expectancy at birth from the Sample Registration System (RBI handbook), by state. "
            "Published for the larger states only; the others are blank.",
            "note": "State-wide values: every hex of a state has the same colour.",
            "values": state_fact("life_expectancy"),
        },
        {
            "id": "pm25", "group": "hazards", "name": "Air pollution", "icon": "l-disasters", "emoji": "🌫️",
            "unit": f"PM2.5, µg/m³ annual mean ({eco.get('pm25_year', '')})", "format": "float", "scale": "linear",
            "ramp": ["#fff1b0", "#e8c95a", "#c5862a", "#8f4a14", "#5a240a", "#2a0e05"], "higher_is": "bad",
            "source": "shrug",
            "description": "Fine-particle air pollution: the annual mean surface PM2.5 estimated from satellites and a "
            "chemical transport model (van Donkelaar et al.), averaged by SHRUG over each 2011 sub-district and here "
            "over each district. India's annual standard is 40 µg/m³; the WHO guideline is 5.",
            "values": spread(eco.get("county_pm25", [None] * len(density_c)), False),
        },
        {
            "id": "quakes", "group": "hazards", "name": "Earthquakes", "icon": "l-disasters", "emoji": "🌋",
            "unit": "quakes of M5.5+ since 1900", "format": "int", "scale": "linear",
            "ramp": ["#1a1414", "#3d2420", "#6e3326", "#a8452a", "#dc6a2e", "#ffb35a"], "higher_is": "bad",
            "source": "usgs_quakes",
            "description": f"Earthquakes of magnitude 5.5 or more since 1900 (USGS catalogue) with an epicentre within "
            f"{QUAKE_RADIUS_KM:.0f} km of the hex centre.",
            "note": "Early-20th-century records are incomplete; zero means none recorded, not no risk.",
            "values": count,
        },
        {
            "id": "quake_max", "group": "hazards", "name": "Strongest quake", "icon": "l-disasters", "emoji": "📉",
            "unit": "magnitude", "format": "float", "scale": "linear", "domain": [5.5, 8.0],
            "ramp": ["#2a2018", "#5a3a20", "#8f5226", "#c2692a", "#e8873a", "#ffc06a"], "higher_is": "bad",
            "source": "usgs_quakes",
            "description": f"The largest magnitude among M5.5+ earthquakes since 1900 within {QUAKE_RADIUS_KM:.0f} km "
            "of the hex centre (USGS catalogue). Blank where none was recorded.",
            "values": maxmag,
        },
    ]
    lenses += health
    pct, cover = world["pct"], world["cover"]
    for lid, (keys, meta) in LAND_LENSES.items():
        values = [round(sum(pct[k][i] for k in keys) / 100, 2) if owner[i] >= 0 and cover[i] else None
                  for i in range(n)]
        lenses.append({"id": lid, "group": "land", **meta, "unit": "share of land", "format": "pct",
                       "scale": "linear", "higher_is": "neutral", "source": "worldcover", "values": values})

    for lens in lenses:
        if "domain" in lens:
            continue
        lens["domain"] = percentile_domain(lens["values"], lens["scale"] == "log")
        lens["description"] += DOMAIN_NOTE
    groups = [g for g in GROUPS if any(l["group"] == g["id"] for l in lenses)]
    write_web("lenses.json", {"vintage": "Census 2011", "groups": groups, "lenses": lenses})
    print(f"    {len(lenses)} lenses; hex area {HEX_AREA_KM2:.0f} km²")
