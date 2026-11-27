"""MoSPI eSankhyiki API (Ministry of Statistics and Programme Implementation): earnings and household spending by state.

Two official surveys, read from the ministry's open API (https://api.mospi.gov.in, the service behind eSankhyiki):

- Periodic Labour Force Survey, calendar year 2025 (PLFS 2025): average monthly earnings of regular wage/salaried
  employees (the preceding calendar month), average daily wage of casual labourers (other than public works), and
  average gross earnings from self-employment in the last 30 days; persons, rural + urban.
- Household Consumption Expenditure Survey 2023-24 (HCES): average monthly spending per person (MPCE), rural and
  urban, without imputation (the survey's headline: what households spent, not counting free items received through
  welfare schemes; the figure with imputation is kept alongside).

Every state and union territory plus All India. Each query is saved as returned; `process` reads only those files.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from ..core.fetch import record
from ..core.source import Source, SourceInfo
from .rbi_states import NAME_TO_FIPS

API = "https://api.mospi.gov.in"
PLFS_YEAR = "PLFS 2025"
HCES_YEAR = "2023-24"
# file -> (endpoint, query)
QUERIES = {
    "plfs_regular_wage.json": ("/api/plfs/getData", {"indicator_code": 6, "frequency_code": 1, "year": PLFS_YEAR,
                                                     "gender_code": 3, "sector_code": 3}),
    "plfs_casual_wage.json": ("/api/plfs/getData", {"indicator_code": 7, "frequency_code": 1, "year": PLFS_YEAR,
                                                    "gender_code": 3, "sector_code": 3}),
    "plfs_self_employed.json": ("/api/plfs/getData", {"indicator_code": 8, "frequency_code": 1, "year": PLFS_YEAR,
                                                      "gender_code": 3, "sector_code": 3}),
    "hces_mpce_rural.json": ("/api/hces/getHcesRecords", {"indicator_code": 1, "year": HCES_YEAR, "sector_code": 1,
                                                          "imputation_type_code": 1}),
    "hces_mpce_urban.json": ("/api/hces/getHcesRecords", {"indicator_code": 1, "year": HCES_YEAR, "sector_code": 2,
                                                          "imputation_type_code": 1}),
    "hces_mpce_rural_imputed.json": ("/api/hces/getHcesRecords", {"indicator_code": 1, "year": HCES_YEAR,
                                                                  "sector_code": 1, "imputation_type_code": 2}),
    "hces_mpce_urban_imputed.json": ("/api/hces/getHcesRecords", {"indicator_code": 1, "year": HCES_YEAR,
                                                                  "sector_code": 2, "imputation_type_code": 2}),
}
KEYS = {"plfs_regular_wage.json": "regular_wage", "plfs_casual_wage.json": "casual_wage",
        "plfs_self_employed.json": "self_employed", "hces_mpce_rural.json": "mpce_rural",
        "hces_mpce_urban.json": "mpce_urban", "hces_mpce_rural_imputed.json": "mpce_rural_imputed",
        "hces_mpce_urban_imputed.json": "mpce_urban_imputed"}


def _get(path, query):
    url = API + path + "?" + urllib.parse.urlencode(query)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "indiaciv-pipeline"}),
                                timeout=60) as r:
        return json.load(r)


def fips_of(name: str) -> str | None:
    n = re.sub(r"\s+", " ", name.strip().lower()).replace(" and ", " & ")
    if n.startswith("dadra & nagar haveli"):
        return "26"  # one UT since 2020 (DNH and Daman & Diu); census code 26
    return NAME_TO_FIPS.get(n)


class Mospi(Source):
    info = SourceInfo(
        id="mospi",
        title="eSankhyiki open API: PLFS 2025 earnings and HCES 2023-24 household spending",
        publisher="Ministry of Statistics and Programme Implementation (MoSPI / NSO), Government of India",
        homepage="https://api.mospi.gov.in",
        license="Government Open Data License - India (attribution: MoSPI)",
        description="Average monthly earnings of salaried employees, daily wages of casual labourers and monthly "
        "earnings from self-employment by state (Periodic Labour Force Survey, calendar year 2025), and average "
        "monthly spending per person, rural and urban, by state (Household Consumption Expenditure Survey 2023-24).",
        used_for=["State earnings and spending facts"],
    )

    def fetch(self, force=False):
        for name, (path, query) in QUERIES.items():
            dest = self.raw_dir / name
            if dest.exists() and not force:
                continue
            rows, page = [], 1
            while True:
                d = _get(path, {**query, "page": page})
                rows += d.get("data") or []
                if page >= (d.get("meta_data") or {}).get("totalPages", 1):
                    break
                page += 1
            if not rows:
                raise SystemExit(f"mospi: {name} returned no rows ({d.get('msg')})")
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps({"query": query, "data": rows}, ensure_ascii=False, indent=1))
            record(self.id, name, API + path + "?" + urllib.parse.urlencode(query), note="all pages, merged")

    def process(self):
        states, unmatched = {}, []
        for name, key in KEYS.items():
            for r in json.loads((self.raw_dir / name).read_text())["data"]:
                f = fips_of(r["state"])
                if f is None:
                    unmatched.append(r["state"])
                    continue
                try:
                    v = float(r["value"])
                except (TypeError, ValueError):
                    continue
                states.setdefault(f, {})[key] = v
        if unmatched:
            raise SystemExit(f"mospi: unmatched state names {sorted(set(unmatched))}")
        print(f"    {len(states) - 1} states/UTs + All India; India regular wage ₹{states['IN']['regular_wage']:,.0f}"
              f"/month, MPCE rural ₹{states['IN']['mpce_rural']:,.0f} urban ₹{states['IN']['mpce_urban']:,.0f}")
        return {"vintage": f"{PLFS_YEAR} (calendar year); HCES {HCES_YEAR}", "_files": sorted(QUERIES),
                "plfs_year": PLFS_YEAR.removeprefix("PLFS "), "hces_year": HCES_YEAR, "states": states}
