"""NFHS-5 district fact sheets matched to today's districts.

NFHS-5 sampled the 707 districts that existed on 31 March 2017; India has redrawn some since. Each fact sheet is matched
to the district of today in the same state with the same name: exact after normalisation, else one name containing the
other (Muktsar / Sri Muktsar Sahib), else a spelling variant within two letters (Gurudaspur / Gurdaspur), else the
2011 census name of the district's main 2011 district. A district of today gets at most one fact sheet, the closest
match; districts created after 2017, and any without a confident match, have no NFHS-5 values (Pending). A district
whose borders changed after 2017 keeps the fact sheet of the 2017 district of its name.

NITI Aayog's district MPI (the same 707 NFHS-5 districts) is matched to today's districts the same way, trying the
name, the part outside brackets and the part inside them ("Allahabad (Prayagraj)"), and added as one more fact.
"""

from __future__ import annotations

import re
from collections import defaultdict

from ..core.store import load_interim, save_interim

REQUIRES = ["_world", "_population", "india_boundaries", "nfhs5", "niti_mpi", "rbi_states"]
PRODUCES = ["_nfhs"]

# Fact-sheet indicator number -> (key, label, higher_is, label prefix of the India fact sheet row)
INDICATORS = {
    7: ("electricity", "Households with electricity", "good", "Population living in households with electricity"),
    8: ("water", "Improved drinking water", "good", "Population living in households with an improved drinking"),
    9: ("sanitation", "Improved sanitation", "good", "Population living in households that use an improved sanit"),
    10: ("clean_fuel", "Clean cooking fuel", "good", "Households using clean fuel for cooking"),
    12: ("insurance", "Health insurance (any household member)", "good", "Households with any usual member covered"),
    14: ("women_literate", "Women who are literate", "good", "Women who are literate"),
    15: ("women_schooling", "Women with 10+ years of schooling", "good", "Women with 10 or more years of schooling"),
    16: ("child_marriage", "Women 20-24 married before 18", "bad", "Women age 20-24 years married before age 18"),
    42: ("institutional_births", "Institutional births", "good", "Institutional births (%)"),
    73: ("stunting", "Children under 5 who are stunted", "bad", "Children under 5 years who are stunted"),
    76: ("underweight", "Children under 5 who are underweight", "bad", "Children under 5 years who are underweight"),
    84: ("anaemia_women", "Women 15-49 who are anaemic", "bad", "All women age 15-49 years who are anaemic"),
}
DROP = re.compile(r"\b(district|dist)\b")
# Official renamings and spellings that the name rules cannot bridge: survey name -> today's boundary-file name.
RENAMED = {"SPSR Nellore": "Sri Potti Sriramulu Nellore", "Dang": "Dangs", "Sonepur": "Subarnapur",
           "Kumuram Bheem Asifabad": "Komarram Bheem", "Komaram Bheem Asifabad": "Komarram Bheem",
           "Wanaparthy": "Wanparti", "Howrah": "Haora", "North 24 Parganas": "North Twenty-four Parganas",
           "Kamrup Metro": "Kamrup Metropolitan", "Kamrup": "Kamrup Rural"}


def norm(s: str) -> str:
    s = DROP.sub(" ", s.lower().replace("&", "and"))
    return re.sub(r"[^a-z]", "", s)


def edit(a, b):
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def score(a: str, b: str) -> int | None:
    """Lower is better; None = no match."""
    if not a or not b:
        return None
    if a == b:
        return 0
    if len(a) >= 5 and len(b) >= 5 and (a in b or b in a):
        return 1
    if len(a) >= 6 and edit(a, b) <= 2:
        return 2
    return None


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("india_boundaries")
    popd = load_interim("_population")
    nf = load_interim("nfhs5")
    cmeta = {c["geoid"]: c for c in bounds["counties"]}
    geoids = world["counties"]
    names = {g: popd["name_fix"].get(g, cmeta[g]["name"]) for g in geoids}
    parent = {g: (popd["districts"][g].get("parent_2011") or {}).get("name", "") for g in geoids}
    by_state = defaultdict(list)
    for g in geoids:
        by_state[cmeta[g]["state_fips"]].append(g)

    # Candidate pairs (score, sheet, district); then greedy best-first so each side is used once.
    pairs = []
    for i, d in enumerate(nf["districts"]):
        title = d["title"] or d["file"].replace("_", " ")
        a = norm(RENAMED.get(title, title))
        for g in by_state.get(d["state"], []):
            s = score(a, norm(names[g]))
            if s is None and parent[g]:
                s2 = score(a, norm(parent[g]))
                s = None if s2 is None else 3 + s2
            if s is not None:
                pairs.append((s, i, g))
    pairs.sort()
    used_sheet, used_g, match = set(), set(), {}
    for s, i, g in pairs:
        if i in used_sheet or g in used_g:
            continue
        used_sheet.add(i)
        used_g.add(g)
        match[g] = (i, s)

    nat = nf.get("national", {})

    def national(prefix):
        for lab, v in nat.items():
            if lab.lower().startswith(prefix.lower()[:40]):
                return v
        return None

    out, pending = {}, []
    for g in geoids:
        if g not in match:
            pending.append({"district": names[g], "why": "no NFHS-5 fact sheet of that name in its state (created "
                                                         "after 2017, or renamed)"})
            continue
        i, s = match[g]
        d = nf["districts"][i]
        facts = []
        for n, (key, label, hi, nat_prefix) in INDICATORS.items():
            v = d["values"].get(str(n))
            if v is None:
                continue
            nv = national(nat_prefix)
            facts.append({"key": key, "label": label + (" (small sample)" if n in d["small"] else ""),
                          "value": round(v / 100, 4), "national": round(nv / 100, 4) if nv is not None else None,
                          "format": "pct", "higher_is": hi, "year": "2019-21",
                          "source": f"NFHS-5 district fact sheet: {d['title']}"})
        out[g] = {"sheet": d["title"], "match": ["exact", "contained", "spelling", "2011 name", "2011 name",
                                                  "2011 name"][s], "facts": facts}
    # NITI Aayog MPI (NFHS-5 districts): headcount ratio, matched like the fact sheets.
    mpi = load_interim("niti_mpi")["districts"]
    st_fips = {norm(st["name"]): st["fips"] for st in bounds["states"]}
    mpi_nat = (load_interim("rbi_states")["tables"].get("mpi", {}).get("IN") or {}).get(
        "NFHS-5 (2019-21) | Headcount Ratio (Per cent)")

    def variants(name):
        out = {norm(name), norm(re.sub(r"\(.*?\)", " ", name)), norm(RENAMED.get(name, ""))}
        out |= {norm(x) for x in re.findall(r"\((.*?)\)", name)}
        return [v for v in out if v]

    pairs = []
    for i, r in enumerate(mpi):
        if r["h_2021"] is None:
            continue
        fips = st_fips.get(norm(r["state"]))
        for g in by_state.get(fips, []):
            best = None
            for a in variants(r["district"]):
                for b, extra in ((norm(names[g]), 0), (norm(parent[g]), 3)):
                    sc = score(a, b)
                    if sc is not None and (best is None or sc + extra < best):
                        best = sc + extra
            if best is not None:
                pairs.append((best, i, g))
    pairs.sort()
    used_row, used_g2, mpi_out = set(), set(), {}
    for sc, i, g in pairs:
        if i in used_row or g in used_g2:
            continue
        used_row.add(i)
        used_g2.add(g)
        r = mpi[i]
        mpi_out[g] = r["district"]
        fact = {"key": "mpi_poor", "label": "Multidimensionally poor (NITI MPI)", "value": round(r["h_2021"], 4),
                "national": round(mpi_nat / 100, 4) if mpi_nat is not None else None, "format": "pct",
                "higher_is": "bad", "year": "2019-21",
                "source": f"NITI Aayog National MPI 2023: {r['district']} ({r['state']})"}
        if g not in out:
            out[g] = {"sheet": None, "match": None, "facts": []}
        out[g]["facts"].append(fact)
        out[g]["mpi_district"] = r["district"]
    mpi_unused = [mpi[i]["district"] for i in range(len(mpi)) if mpi[i]["h_2021"] is not None and i not in used_row]
    mpi_pending = [{"district": names[g], "why": "no NITI MPI district of that name in its state (created after "
                                                "2017, or renamed)"} for g in geoids if g not in mpi_out]
    unused = [nf["districts"][i]["title"] for i in range(len(nf["districts"])) if i not in used_sheet]
    STATE_NAMES = {"Andaman & Nicobar Islands": "35", "Andhra Pradesh": "28", "Arunachal Pradesh": "12",
                   "Assam": "18", "Bihar": "10", "Chandigarh": "04", "Chhattisgarh": "22",
                   "Dadra & Nagar Haveli and Daman & Diu": "26", "NCT Delhi": "07", "Goa": "30", "Gujarat": "24",
                   "Haryana": "06", "Himachal Pradesh": "02", "Jammu & Kashmir": "01", "Jharkhand": "20",
                   "Karnataka": "29", "Kerala": "32", "Ladakh": "37", "Lakshadweep": "31", "Madhya Pradesh": "23",
                   "Maharashtra": "27", "Manipur": "14", "Meghalaya": "17", "Mizoram": "15", "Nagaland": "13",
                   "Odisha": "21", "Puducherry": "34", "Punjab": "03", "Rajasthan": "08", "Sikkim": "11",
                   "Tamil Nadu": "33", "Telangana": "36", "Tripura": "16", "Uttar Pradesh": "09",
                   "Uttarakhand": "05", "West Bengal": "19"}
    states_out = {}
    for sname, vals in nf.get("states", {}).items():
        fips = STATE_NAMES.get(sname)
        if not fips:
            continue
        facts = []
        for n, (key, label, hi, prefix) in INDICATORS.items():
            v = next((x for lab, x in vals.items() if lab.lower().startswith(prefix.lower()[:40])), None)
            if v is None:
                continue
            nv = national(prefix)
            facts.append({"key": key, "label": label, "value": round(v / 100, 4),
                          "national": round(nv / 100, 4) if nv is not None else None, "format": "pct",
                          "higher_is": hi, "year": "2019-21", "source": f"NFHS-5 state fact sheet: {sname}"})
        states_out[fips] = facts
    keys = {v[0]: {"label": v[1], "higher_is": v[2]} for v in INDICATORS.values()}
    keys["mpi_poor"] = {"label": "Multidimensionally poor (NITI MPI)", "higher_is": "bad"}
    save_interim("_nfhs", {"districts": out, "states": states_out, "pending": pending, "unused_sheets": unused,
                           "mpi_pending": mpi_pending, "mpi_unused": mpi_unused, "keys": keys})
    kinds = defaultdict(int)
    for v in out.values():
        if v["match"]:
            kinds[v["match"]] += 1
    print(f"    {sum(1 for v in out.values() if v['sheet'])} of {len(geoids)} districts have an NFHS-5 fact sheet {dict(kinds)}; "
          f"{len(unused)} sheets unmatched: {unused[:15]}")
    print(f"    {len(mpi_out)} districts have a NITI MPI value; {len(mpi_unused)} MPI rows unmatched: {mpi_unused[:15]}")
