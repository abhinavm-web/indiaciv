"""Census of India 2011, Table A-02: decadal variation in population since 1901, by state and 2011 district.

Each state's A-02 table gives the population at every census from 1901 to 2011, recomputed for the 2011 boundaries of
the state and of each 2011 district. `fetch` finds the 36 tables (India + states/UTs) through the census digital
library's catalogue search ("PC11_A02") and downloads each one's Excel file from its catalogue page.
"""

from __future__ import annotations

import json
import re

from ..core import xlsx
from ..core.source import Source, SourceInfo

NADA = "https://censusindia.gov.in/nada/index.php"
SEARCH = f"{NADA}/api/catalog/search?sk=PC11_A02&ps=60"


def _num(v):
    return int(round(v)) if isinstance(v, (int, float)) else None


class CensusA02(Source):
    info = SourceInfo(
        id="census_a02",
        title="Census of India 2011, A-02: Decadal variation in population since 1901",
        publisher="Office of the Registrar General & Census Commissioner, India (Ministry of Home Affairs)",
        homepage=f"{NADA}/catalog/43333",
        license="Government of India open data (attribution: ORGI, Census 2011)",
        description="Population at every census from 1901 to 2011 for India, each state / UT and each 2011 district, "
        "on their 2011 boundaries. Used for growth from 2001 to 2011 and for the long population series.",
        used_for=["Population growth 2001-2011", "Population history 1901-2011"],
    )

    def fetch(self, force=False):
        idx = self.download(SEARCH, "catalog_search.json", force=force)
        rows = json.loads(idx.read_text(encoding="utf-8"))["result"]["rows"]
        tables = [r for r in rows if re.fullmatch(r"PC11_A02-\d\d", r.get("idno", ""))]
        if len(tables) < 36:
            raise SystemExit(f"census_a02: catalogue search found {len(tables)} A-02 tables, expected 36")
        for r in tables:
            code = r["idno"][-2:]
            rel = f"A02-{code}.xlsx"
            if (self.raw_dir / rel).exists() and not force:
                continue
            page = self.download(f"{NADA}/catalog/{r['id']}", f"pages/{r['id']}.html", force=force)
            html = page.read_text(encoding="utf-8", errors="ignore")
            links = re.findall(r'href="([^"]+/download/\d+/[^"]+\.xlsx?)"', html)
            if not links:
                print(f"    {r['idno']}: no Excel file on its catalogue page")
                continue
            url = links[0]
            if url.lower().endswith(".xlsx"):
                path = self.download(url, rel, force=force)
                if path.read_bytes()[:2] != b"PK":
                    self.discard(rel)
                    print(f"    {r['idno']}: download is not an Excel file")
                continue
            # Old binary .xls: kept as downloaded, plus a CSV copy for the standard-library process step. Reading
            # .xls needs xlrd (pip install xlrd), at fetch time only, like rasterio for WorldCover.
            src = self.download(url, f"A02-{code}.xls", force=force)
            try:
                import xlrd
            except ImportError as exc:  # pragma: no cover
                raise SystemExit("census_a02 fetch needs xlrd for the .xls tables: pip install xlrd") from exc
            import csv
            book = xlrd.open_workbook(src)
            sh = book.sheet_by_index(0)
            out = self.raw_dir / f"A02-{code}.csv"
            with open(out, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                for i in range(sh.nrows):
                    w.writerow(sh.row_values(i))
            from ..core import fetch as core_fetch
            core_fetch.record(self.id, f"A02-{code}.csv", url, note="first sheet of the .xls, converted to CSV with xlrd")

    def process(self):
        series, names, files = {}, {}, []
        def table(path):
            if path.suffix == ".csv":
                import csv
                with open(path, encoding="utf-8", newline="") as f:
                    for r in csv.reader(f):
                        yield [(float(c) if re.fullmatch(r"-?\d+(\.\d+)?", c.strip()) and not re.fullmatch(
                            r"0\d+", c.strip()) else (c if c != "" else None)) for c in r]
            else:
                yield from xlsx.rows(path)

        paths = sorted(list(self.raw_dir.glob("A02-*.xlsx")) + list(self.raw_dir.glob("A02-*.csv")))
        for path in paths:
            files.append(path.name)
            key, last_st = None, None
            for r in table(path):
                r = list(r) + [None] * 6
                c0, c1 = r[0], r[1]
                if c0 is None and last_st and c1 is not None and isinstance(r[2], str) and r[2].strip() and \
                        re.fullmatch(r"\d{1,3}", str(c1).strip().split(".")[0]):
                    c0 = last_st  # some tables leave the state code blank on later districts (Tamil Nadu)
                if isinstance(c0, float) and c0 == int(c0) and isinstance(c1, (float, str)) and r[2]:
                    c0 = f"{int(c0):02d}"
                    c1 = f"{int(float(c1)):03d}" if not isinstance(c1, str) or c1.strip().isdigit() else c1
                if isinstance(c0, str) and re.fullmatch(r"\d{1,2}", c0.strip()) and isinstance(c1, (str, float)) and \
                        re.fullmatch(r"\d{1,3}", str(c1).strip().split(".")[0]) and isinstance(r[2], str):
                    st, dt = c0.strip().zfill(2), str(c1).strip().split(".")[0].zfill(3)
                    last_st = st
                    key = "IN" if st == "00" and dt == "000" else (st if dt == "000" else f"{st}{dt}")
                    names[key] = (r[2] or "").strip()
                # Year cells can carry footnote marks ("2001 ++", "1981 #": estimated or partly enumerated
                # censuses, as footnoted in the table).
                ym = re.search(r"(19|20)\d\d", str(int(r[3])) if isinstance(r[3], float) else str(r[3] or ""))
                if key is None or not ym:
                    continue
                series.setdefault(key, {})[ym.group(0)] = _num(r[4])
        n_dist = sum(1 for k in series if len(k) == 5)
        print(f"    {len(files)} tables; {sum(1 for k in series if len(k) == 2)} states, {n_dist} districts; "
              f"India 2001 {series.get('IN', {}).get('2001')}, 2011 {series.get('IN', {}).get('2011')}")
        return {"vintage": "Census 2011, Table A-02", "_files": files, "series": series, "names": names}
