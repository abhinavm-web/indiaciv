"""SHRUG (Socioeconomic High-resolution Rural-Urban Geographic Platform for India), version 2.2, Development Data Lab.

SHRUG links India's censuses to consistent small areas ("shrids": villages and towns on boundaries that hold from
1991 to 2011) and to urban areas drawn from 2023 night-time lights (SHRUG's "ua", each named after its main 2011
town). Used here, at those two levels and at 2011 sub-districts:

- population at the 2001 and 2011 censuses on the same urban area (city growth on fixed boundaries);
- employment in establishments at the 2013 Economic Census (MoSPI), by SHRUG's industry codes (city and district jobs);
- SHRUG's estimate of urban consumption per person and the urban poverty rate, from the 2011 SECC (a model
  estimate by the SHRUG authors, labelled as such);
- surface PM2.5 (van Donkelaar et al., satellite-based annual estimates), by 2011 sub-district.

The download page hands out signed links that expire, so the fetch asks it for fresh ones each time. Licence:
CC BY-NC-SA 4.0 (non-commercial, share-alike); data linked to SHRUG must be posted with SHRUG identifiers.
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
import zipfile

from ..core import fetch as core_fetch
from ..core.source import Source, SourceInfo

INDEX = "https://www.devdatalab.org/shrug_download/data"
# module file stem in the signed URL -> members to keep (name in zip -> name in raw/)
MODULES = {
    "shrug-pc-keys-csv": {"pc11u_shrid_key.csv": "pc11u_shrid_key.csv"},
    "shrug-shrid-keys-csv": {"viirs_2023_7_5_500_ua_shrid2_key.csv": "ua_shrid2_key.csv"},
    "shrug-pca01-csv": {"pc01_pca_clean_ua.csv": "pc01_pca_ua.csv"},
    "shrug-pca11-csv": {"pc11_pca_clean_ua.csv": "pc11_pca_ua.csv"},
    "shrug-ec13-csv": {"ec13_ua.csv": "ec13_ua.csv", "ec13_pc11subdist.csv": "ec13_pc11subdist.csv",
                       "README.md": "README.md"},
    "shrug-secc-cons-urban-csv": {"secc_cons_urban_ua.csv": "secc_cons_urban_ua.csv"},
    "shrug-pm25-csv": {"pm25_pc11subdist.csv": "pm25_pc11subdist.csv"},
    "shrug-shric-desc-csv": {"shric_descriptions.csv": "shric_descriptions.csv"},
}
PM25_KEEP_FROM = 2011  # the sub-district PM2.5 table runs 1998-2020; keep 2011 on
# SHRUG industry codes (shric, 1-90) grouped into the sectors shown on the map.
SECTORS = [
    ("manufacturing", "Manufacturing", list(range(5, 19)) + list(range(21, 33)) + [72]),
    ("mining_energy", "Mining, energy and utilities", [3, 4, 19, 20, 33, 34, 35]),
    ("construction", "Construction", [36, 37, 38]),
    ("trade", "Shops, trade and repairs", list(range(39, 51))),
    ("hospitality", "Hotels and restaurants", [51, 52]),
    ("transport", "Transport, storage and post", list(range(53, 64))),
    ("it_telecom", "IT, software and telecoms", [64, 73]),
    ("finance", "Finance, insurance and real estate", [65, 66, 67, 68, 69]),
    ("business", "Professional and business services", [70, 71, 74, 75, 76, 77, 78, 79, 87]),
    ("education", "Education", [80]),
    ("health", "Health and social work", [81, 82, 83]),
    ("other_services", "Community, personal and other services", [84, 85, 86, 88, 89, 90]),
    ("farm_allied", "Forestry and fishing", [1, 2]),
]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _sectors(row):
    out = {}
    for key, _, codes in SECTORS:
        vals = [_f(row.get(f"ec13_emp_shric_{c}")) for c in codes]
        out[key] = round(sum(v for v in vals if v is not None))
    return out


class Shrug(Source):
    info = SourceInfo(
        id="shrug",
        title="SHRUG v2.2: census, Economic Census 2013, SECC consumption and PM2.5 on consistent areas",
        publisher="Development Data Lab (Asher, Lunt, Matsuura and Novosad)",
        homepage="https://www.devdatalab.org/shrug_download/",
        license="CC BY-NC-SA 4.0 (non-commercial, share-alike)",
        description="India's 2001 and 2011 censuses, the 2013 Economic Census, SHRUG's SECC-based urban "
        "consumption estimates and satellite PM2.5, aggregated by SHRUG to consistent urban areas and 2011 "
        "sub-districts.",
        used_for=["City growth on fixed boundaries", "City and district jobs (Economic Census 2013)",
                  "City consumption estimate", "Air pollution lens"],
    )

    def fetch(self, force=False):
        need = [m for m, files in MODULES.items() if force or not all((self.raw_dir / f).exists()
                                                                       for f in files.values())]
        if not need:
            return
        with urllib.request.urlopen(urllib.request.Request(INDEX, headers={"User-Agent": "indiaciv-pipeline"}),
                                    timeout=120) as r:
            index = json.load(r)
        urls = {}
        for row in index:
            for key in ("secondary_download", "primary_download"):
                stem = re.search(r"/([^/?]+)\.zip", row.get(key) or "")
                if stem:
                    urls.setdefault(stem.group(1), row[key])
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        for module in need:
            url = urls.get(module)
            if not url:
                raise SystemExit(f"shrug: module {module} is not on the download page any more")
            print(f"    ↓ {module}.zip")
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "indiaciv-pipeline"}),
                                        timeout=1800) as r:
                blob = r.read()
            plain = url.split("?")[0]
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                for member, name in MODULES[module].items():
                    dest = self.raw_dir / name
                    if member == "pm25_pc11subdist.csv":  # keep the recent years only
                        with z.open(member) as f, open(dest, "w", encoding="utf-8", newline="") as out:
                            rd = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                            w = csv.DictWriter(out, fieldnames=rd.fieldnames)
                            w.writeheader()
                            w.writerows(r for r in rd if int(float(r["year"])) >= PM25_KEEP_FROM)
                    else:
                        dest.write_bytes(z.read(member))
                    core_fetch.record(self.id, name, plain, note=f"{member} from {module}.zip (signed link)")

    def process(self):
        d = self.raw_dir

        def rows(name):
            with open(d / name, encoding="utf-8", newline="") as f:
                yield from csv.DictReader(f)

        town_shrid = {r["pc11_town_id"]: r["shrid2"] for r in rows("pc11u_shrid_key.csv")}
        shrid_ua = {r["shrid2"]: r["ua_id"] for r in rows("ua_shrid2_key.csv")}
        town_ua = {t: shrid_ua[s] for t, s in town_shrid.items() if s in shrid_ua}
        ua = {}
        for r in rows("pc11_pca_ua.csv"):
            ua.setdefault(r["ua_id"], {})["pop2011"] = _f(r["pc11_pca_tot_p"])
        for r in rows("pc01_pca_ua.csv"):
            ua.setdefault(r["ua_id"], {})["pop2001"] = _f(r["pc01_pca_tot_p"])
        for r in rows("ec13_ua.csv"):
            ua.setdefault(r["ua_id"], {}).update({"emp": _f(r["ec13_emp_all"]), "emp_sectors": _sectors(r)})
        for r in rows("secc_cons_urban_ua.csv"):
            ua.setdefault(r["ua_id"], {}).update({"cons_pc": _f(r["secc_cons_pc_urban"]),
                                                  "pov_rate": _f(r["secc_pov_rate_urban"])})
        sub = {}
        for r in rows("ec13_pc11subdist.csv"):
            key = r["pc11_state_id"] + r["pc11_district_id"] + r["pc11_subdistrict_id"]
            sub[key] = {"emp": _f(r["ec13_emp_all"]), "emp_sectors": _sectors(r)}
        last = max(int(float(r["year"])) for r in rows("pm25_pc11subdist.csv"))
        for r in rows("pm25_pc11subdist.csv"):
            if int(float(r["year"])) != last:
                continue
            key = r["pc11_state_id"] + r["pc11_district_id"] + r["pc11_subdistrict_id"]
            sub.setdefault(key, {}).update({"pm25": _f(r["pm25_mean"]), "pm25_cells": _f(r["pm25_num_cells"])})
        nat = {k: sum(s.get("emp_sectors", {}).get(k, 0) for s in sub.values()) for k, _, _ in SECTORS}
        nat_emp = sum(s.get("emp") or 0 for s in sub.values())
        print(f"    {len(town_ua)} towns in {len(ua)} SHRUG urban areas; {len(sub)} sub-districts; EC13 employment "
              f"{nat_emp:,.0f}; PM2.5 year {last}")
        return {"vintage": "SHRUG v2.2 (Development Data Lab)", "_files": sorted({n for m in MODULES.values()
                                                                                for n in m.values()}),
                "town_ua": town_ua, "ua": ua, "subdistricts": sub, "pm25_year": last,
                "sectors": [{"key": k, "label": lab} for k, lab, _ in SECTORS],
                "national": {"emp": nat_emp, "emp_sectors": nat}}
