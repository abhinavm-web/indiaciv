"""Census of India 2011, Primary Census Abstract: population, households, literacy and workers.

Two tables from the Office of the Registrar General & Census Commissioner (ORGI) digital library:

* "Basic Population Figures of India/State/District/Sub-District/Town - 2011" (catalogue 42559): one row per area and
  Total/Rural/Urban, for India, the 35 states/UTs of 2011, 640 districts, 5,988 sub-districts and 8,397 towns.
* "Primary Census Abstract - Urban Agglomeration India - 2011" (catalogue 45261): the urban agglomerations (UAs) and
  their constituent towns, with the same columns.

2011 is the latest census India has published; the next count's results are not out. Areas are 2011 areas: the census
builder moves sub-district counts onto today's districts.
"""

from __future__ import annotations

from ..core import xlsx
from ..core.source import Source, SourceInfo

PCA = ("https://censusindia.gov.in/nada/index.php/catalog/42559/download/46185/"
       "2011-IndiaStateDistSbDistTwn-0000.xlsx")
UA = "https://censusindia.gov.in/nada/index.php/catalog/45261/download/48987/PCA11-UA-0000.xlsx"
PCA_FILE = "2011-IndiaStateDistSbDistTwn-0000.xlsx"
UA_FILE = "PCA11-UA-0000.xlsx"

# Columns kept (Primary Census Abstract names). Persons only; caste columns are not used by this map.
COLS = ["No_HH", "TOT_P", "TOT_M", "TOT_F", "P_06", "P_LIT", "TOT_WORK_P", "MAINWORK_P", "MAIN_CL_P", "MAIN_AL_P",
        "MAIN_HH_P", "MAIN_OT_P", "MARGWORK_P", "MARG_CL_P", "MARG_AL_P", "MARG_HH_P", "MARG_OT_P", "NON_WORK_P"]


def _int(v):
    if isinstance(v, float):
        return int(round(v))
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


class Census2011(Source):
    info = SourceInfo(
        id="census2011",
        title="Census of India 2011: Primary Census Abstract (population, households, literacy, workers)",
        publisher="Office of the Registrar General & Census Commissioner, India (Ministry of Home Affairs)",
        homepage="https://censusindia.gov.in/nada/index.php/catalog/42559",
        license="Government of India open data (attribution: ORGI, Census 2011)",
        description="Population, households, children 0-6, literates and workers (main and marginal, by "
        "cultivators, agricultural labourers, household industry and other workers) for India, every state, "
        "district, sub-district and town, by total / rural / urban; plus the urban agglomerations (catalogue "
        "45261). 2011 is the latest census with published results.",
        used_for=["Population of states, districts and cities", "Urbanisation, literacy, households",
                  "Workers by sector (Food and Production yields)", "Cities (urban agglomerations and towns)"],
    )

    def fetch(self, force=False):
        self.download(PCA, PCA_FILE, force=force, expect_binary=True)
        self.download(UA, UA_FILE, force=force, expect_binary=True)

    def process(self):
        rows = xlsx.rows(self.raw_dir / PCA_FILE, "Data")
        head = next(rows)
        ix = {h: k for k, h in enumerate(head)}
        nation, states, districts, subs, towns = {}, {}, {}, {}, []
        for r in rows:
            level, tru = r[ix["Level"]], r[ix["TRU"]]
            rec = {c: _int(r[ix[c]]) for c in COLS}
            st, dt, sdt, town = r[ix["State"]], r[ix["District"]], r[ix["Subdistt"]], r[ix["Town/Village"]]
            name = (r[ix["Name"]] or "").strip()
            if level == "TOWN":
                towns.append({"st": st, "dt": dt, "sdt": sdt, "town": town, "name": name, **rec})
                continue
            key = {"India": None, "STATE": st, "DISTRICT": f"{st}{dt}", "SUB-DISTRICT": f"{st}{dt}{sdt}"}[level]
            table = {"India": None, "STATE": states, "DISTRICT": districts, "SUB-DISTRICT": subs}[level]
            target = nation if table is None else table.setdefault(key, {"name": name})
            target[tru.lower()] = rec

        uas = []
        rows = xlsx.rows(self.raw_dir / UA_FILE, "Data")
        head = next(rows)
        ix = {h: k for k, h in enumerate(head)}
        for r in rows:
            lvl = _int(r[ix["Level"]])
            rec = {c: _int(r[ix[c]]) for c in COLS}
            item = {"level": lvl, "ua": r[ix["UA Code"]], "name": (r[ix["UA Name"]] or "").strip(),
                    "st": r[ix["ST Code"]], "dt": r[ix["DT Code"]], "sdt": r[ix["SubDT Code"]],
                    "town": r[ix["Town Code"]], **rec}
            uas.append(item)
        tot = nation["total"]["TOT_P"]
        print(f"    India {tot:,}; {len(states)} states, {len(districts)} districts, {len(subs)} sub-districts, "
              f"{len(towns)} towns, {sum(1 for u in uas if u['level'] == 0)} urban agglomerations")
        return {
            "vintage": "Census 2011, Primary Census Abstract",
            "_files": [PCA_FILE, UA_FILE],
            "columns": COLS,
            "nation": nation, "states": states, "districts": districts, "subdistricts": subs,
            "towns": towns, "uas": uas,
        }
