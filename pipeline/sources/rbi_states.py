"""Reserve Bank of India, Handbook of Statistics on Indian States: state GDP and value added by sector.

The handbook's page lists every table with a link to an Excel file. `fetch` reads the page, finds the tables this map
uses by their number and title, and downloads them (the file names carry the edition date, so a new edition is a new
cached file). Figures are the National Statistical Office's (MoSPI) state accounts, base 2011-12, in ₹ lakh at current
prices.
"""

from __future__ import annotations

import re

from ..core import xlsx
from ..core.source import Source, SourceInfo

PAGE = "https://www.rbi.org.in/Scripts/AnnualPublications.aspx?head=Handbook+of+Statistics+on+Indian+States"
TABLES = {
    21: ("gsdp", "Gross State Domestic Product (Current Prices)"),
    19: ("nsdp_per_capita", "Per Capita Net State Domestic Product (Current Prices)"),
    29: ("gsva_agriculture", "Gross State Value Added by Economic Activity - Agriculture (Current Prices)"),
    33: ("gsva_manufacturing", "Gross State Value Added by Economic Activity - Manufacturing (Current Prices)"),
    41: ("gsva_industry", "Gross State Value Added by Economic Activity - Industry (Current Prices)"),
    49: ("gsva_services", "Gross State Value Added by Economic Activity - Services (Current Prices)"),
}
LINK = re.compile(r"href=PublicationsView\.aspx\?id=\d+>\s*Table\s*(\d+):?\s*([^<]+?)\s*</a></td><td\s+nowrap\s*>"
                  r"<a id='ADOC_[^']+' target='_blank' href='([^']+\.XLSX)'", re.I)

# Handbook names -> 2011 census state codes (india_boundaries "fips").
NAME_TO_FIPS = {
    "andaman & nicobar islands": "35", "andhra pradesh": "28", "arunachal pradesh": "12", "assam": "18",
    "bihar": "10", "chandigarh": "04", "chhattisgarh": "22", "delhi": "07", "goa": "30", "gujarat": "24",
    "haryana": "06", "himachal pradesh": "02", "jammu & kashmir": "01", "jharkhand": "20", "karnataka": "29",
    "kerala": "32", "ladakh": "37", "madhya pradesh": "23", "maharashtra": "27", "manipur": "14",
    "meghalaya": "17", "mizoram": "15", "nagaland": "13", "odisha": "21", "puducherry": "34", "punjab": "03",
    "rajasthan": "08", "sikkim": "11", "tamil nadu": "33", "telangana": "36", "tripura": "16",
    "uttar pradesh": "09", "uttarakhand": "05", "west bengal": "19",
    "dadra & nagar haveli and daman & diu": "26", "lakshadweep": "31",
}


def _num(v):
    return float(v) if isinstance(v, (int, float)) else None


def _norm(name: str) -> str:
    return re.sub(r"[*#@\s]+$", "", name.strip()).lower().replace(" and ", " & ").replace("  ", " ")


class RbiStates(Source):
    info = SourceInfo(
        id="rbi_states",
        title="Handbook of Statistics on Indian States (state GDP and value added by sector)",
        publisher="Reserve Bank of India; figures from the National Statistical Office (MoSPI)",
        homepage=PAGE,
        license="Reserve Bank of India publication (free to use with attribution)",
        description="Gross State Domestic Product, per-capita Net State Domestic Product and Gross State Value "
        "Added in agriculture, manufacturing, industry and services, at current prices (base 2011-12), in ₹ lakh "
        "(1 lakh = 100,000). States that have not published a year are blank for it.",
        used_for=["Gold (state GDP)", "State economy by sector", "GDP per person"],
    )

    def _links(self):
        page = self.download(PAGE, "handbook_page.html", force=True)
        found = {}
        for m in LINK.finditer(page.read_text(encoding="utf-8", errors="ignore")):
            found[int(m.group(1))] = (m.group(2).strip(), m.group(3))
        return found

    def fetch(self, force=False):
        links = self._links()
        for n, (key, title) in TABLES.items():
            if n not in links:
                raise SystemExit(f"RBI handbook: table {n} ({title}) not found on {PAGE}")
            got, url = links[n]
            if title.lower().split(" (")[0] not in got.lower():
                raise SystemExit(f"RBI handbook: table {n} is now {got!r}, expected {title!r}")
            rel = f"T{n}_{url.rsplit('/', 1)[-1]}"
            # rbidocs serves these workbooks as Content-Type text/html, so check the file itself is a zip (xlsx).
            # rbidocs answers a browser-like or custom User-Agent with a JavaScript challenge page, but serves the
            # file to Python's default one.
            path = self.download(url, rel, force=force, headers={"User-Agent": "Python-urllib/3"})
            if path.read_bytes()[:2] != b"PK":
                self.discard(rel)
                raise SystemExit(f"RBI handbook: {url} is not an Excel file")

    def _file(self, n):
        files = sorted(p for p in self.raw_dir.glob(f"T{n}_*.XLSX"))
        if not files:
            raise SystemExit(f"rbi_states: table {n} not fetched")
        return files[-1]

    def process(self):
        out, used, unmatched = {}, [], set()
        for n, (key, _title) in TABLES.items():
            path = self._file(n)
            used.append(path.name)
            series: dict[str, dict[str, float | None]] = {}
            for sheet in xlsx.sheets(path):
                years = None
                for r in xlsx.rows(path, sheet):
                    cells = [c for c in r]
                    if years is None:
                        ys = [c for c in cells if isinstance(c, str) and re.fullmatch(r"\d{4}-\d{2}", c.strip())]
                        if len(ys) >= 2:
                            years = {k: c.strip() for k, c in enumerate(cells)
                                     if isinstance(c, str) and re.fullmatch(r"\d{4}-\d{2}", c.strip())}
                        continue
                    name = cells[1] if len(cells) > 1 else None
                    if not isinstance(name, str) or not name.strip():
                        continue
                    fips = NAME_TO_FIPS.get(_norm(name))
                    if fips is None:
                        if not re.match(r"^[-*#@]|^source|^note|^all india|^\(", name.strip().lower()):
                            unmatched.add(name.strip())
                        continue
                    rec = series.setdefault(fips, {})
                    for k, y in years.items():
                        if k < len(cells):
                            rec[y] = _num(cells[k])
            out[key] = series
        if unmatched:
            print(f"    rows not matched to a state: {sorted(unmatched)}")
        years = sorted({y for s in out["gsdp"].values() for y, v in s.items() if v is not None})
        print(f"    {len(out['gsdp'])} states with GSDP; years {years[0]} to {years[-1]}")
        return {"vintage": f"RBI Handbook of Statistics on Indian States ({used[0].split('_')[1][:8]})",
                "_files": used, "unit": "INR lakh", "tables": out}
