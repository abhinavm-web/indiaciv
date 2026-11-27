"""Official population projections for India and its states, 2011-2036 (Report of the Technical Group on Population
Projections, National Commission on Population, Ministry of Health and Family Welfare; report dated November 2019,
published July 2020).

Table 11 gives the projected total population on 1 July of each year, in thousands, for India and each state / UT
(Jammu & Kashmir and Ladakh separately; Dadra & Nagar Haveli and Daman & Diu separately, added together here for
today's merged UT). The table prints three states per page; a state's name can run over two header lines, so each
header word is assigned to the state column it sits above. Reading the PDF needs `pdftotext` (poppler-utils), at
fetch time only; the fetch writes one tab-separated table that `process` reads with the standard library.
"""

from __future__ import annotations

import csv
import re
import subprocess

from ..core import fetch as core_fetch
from ..core.source import Source, SourceInfo

URL = "https://nhm.gov.in/New_Updates_2018/Report_Population_Projection_2019.pdf"
PDF = "Report_Population_Projection_2019.pdf"
TABLE = "table11_total_population_1july.tsv"
YEAR = re.compile(r"^\s*(20[1-3]\d)\s*(.*)$")
NUMS = re.compile(r"\d[\d,]*")
# Table header names -> 2011 census state code of today's state / UT.
FIPS = {
    "INDIA": "IN", "JAMMU & KASHMIR (UT)": "01", "HIMACHAL PRADESH": "02", "PUNJAB": "03", "CHANDIGARH": "04",
    "UTTARAKHAND": "05", "HARYANA": "06", "NCT OF DELHI": "07", "RAJASTHAN": "08", "UTTAR PRADESH": "09",
    "BIHAR": "10", "SIKKIM": "11", "ARUNACHAL PRADESH": "12", "NAGALAND": "13", "MANIPUR": "14", "MIZORAM": "15",
    "TRIPURA": "16", "MEGHALAYA": "17", "ASSAM": "18", "WEST BENGAL": "19", "JHARKHAND": "20", "ODISHA": "21",
    "CHHATTISGARH": "22", "MADHYA PRADESH": "23", "GUJARAT": "24", "DAMAN & DIU": "26",
    "DADRA & NAGAR HAVELI": "26", "MAHARASHTRA": "27", "ANDHRA PRADESH": "28", "KARNATAKA": "29", "GOA": "30",
    "LAKSHADWEEP": "31", "KERALA": "32", "TAMIL NADU": "33", "PUDUCHERRY": "34",
    "ANDAMAN & NICOBAR ISLANDS": "35", "TELANGANA": "36", "LADAKH": "37",
}


def parse_table11(text: str) -> list[list]:
    """Rows [state name, year, persons ('000)] from Table 11 of the report's text (pdftotext -layout)."""
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if re.search(r"TABLE\s*[–-]\s*11\s*$", l.strip()))
    stop = next(i for i in range(start, len(lines)) if re.search(r"TABLE\s*[–-]\s*12\s*$", lines[i].strip()))
    out, words, cols, year = [], [], None, None
    for line in lines[start:stop]:
        t = line.strip()
        if re.search(r"TABLE\s*[–-]\s*11", t):
            words, cols, year = [], None, None  # a new page of the table
            continue
        head = re.sub(r"^(\s*)Year\b", lambda m: m.group(1) + "    ", line)  # "Year" can share a line with a name
        if head.strip() and re.fullmatch(r"[A-Z&().'\s-]+", head.strip()) and "TERRITORIES" not in head:
            for m in re.finditer(r"\S+(?: \S+)*", head):  # header words, with their position on the line
                if m.group() != "Year":
                    words.append((m.start() + len(m.group()) / 2, m.group()))
            continue
        if re.fullmatch(r"1(\s+\d+)+", t):  # the column-number row: 1 = Year, then Persons / Male / Female per state
            pos = [m.start() + len(m.group()) / 2 for m in re.finditer(r"\d+", line)][1:]
            mids = [pos[k + 1] for k in range(0, len(pos) - 2, 3)]
            names = [[] for _ in mids]
            for x, w in words:
                names[min(range(len(mids)), key=lambda k: abs(mids[k] - x))].append(w)
            cols = [" ".join(n) for n in names]
            continue
        m = YEAR.match(line)
        if m and cols:
            year, rest = m.group(1), m.group(2)
        elif year and cols and NUMS.search(t) and not t[:1].isalpha():
            rest = line  # the year on a line of its own, the numbers on the next
        else:
            continue
        nums = [int(x.replace(",", "")) for x in NUMS.findall(rest)]
        if len(nums) == 3 * len(cols):
            out += [[cols[k], int(year), nums[3 * k]] for k in range(len(cols))]
            year = None
    return out


class PopProjections(Source):
    info = SourceInfo(
        id="pop_projections",
        title="Population Projections for India and States 2011-2036 (Technical Group, Table 11)",
        publisher="National Commission on Population, Ministry of Health and Family Welfare",
        homepage="https://nhm.gov.in/New_Updates_2018/Report_Population_Projection_2019.pdf",
        license="Government of India publication (attribution: MoHFW / National Commission on Population)",
        description="Projected total population of India and each state / UT on 1 July of each year, 2011-2036, "
        "by the cohort-component method from the 2011 census.",
        used_for=["State population projections", "Derived district population estimates"],
    )

    def fetch(self, force=False):
        dest = self.raw_dir / TABLE
        if dest.exists() and not force:
            return
        pdf = self.download(URL, PDF, force=force, expect_binary=True)
        text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
        rows = parse_table11(text)
        with open(dest, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["state", "year", "persons_thousands"])
            w.writerows(rows)
        core_fetch.record(self.id, TABLE, URL, note="Table 11, persons column")

    def process(self):
        series, unknown = {}, set()
        with open(self.raw_dir / TABLE, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                fips = FIPS.get(re.sub(r"\s+", " ", r["state"]).strip())
                if not fips:
                    unknown.add(r["state"])
                    continue
                s = series.setdefault(fips, {})
                s[r["year"]] = s.get(r["year"], 0) + int(r["persons_thousands"]) * 1000
        if unknown:
            raise SystemExit(f"pop_projections: unknown state names in Table 11: {sorted(unknown)}")
        print(f"    {len(series)} series (India and states/UTs), years {min(series['IN'])}-{max(series['IN'])}")
        return {"vintage": "Technical Group projections, 1 July (report of November 2019)", "_files": [TABLE],
                "series": series}
