"""NITI Aayog's National Multidimensional Poverty Index (Progress Review 2023): headcount, intensity and MPI for the
707 districts of NFHS-5 (2019-21), with the NFHS-4 (2015-16) values beside them.

The figures are only published inside the report's PDF, one "Overview of Districts" table per state. The PDF carries a
hidden copy of the previous state's table under some pages (drawn first, then covered by the table's background), so
the fetch keeps only the text drawn after the page's last table background. Reading the PDF's drawing order needs
PyMuPDF (`pip install pymupdf`), at fetch time only; the fetch writes one tab-separated table that `process` reads
with the standard library. A long district name that wraps onto two lines is joined.
"""

from __future__ import annotations

import collections
import csv
import re
import unicodedata

from ..core import fetch as core_fetch
from ..core.source import Source, SourceInfo

URL = "https://www.niti.gov.in/sites/default/files/2023-08/India-National-Multidimentional-Poverty-Index-2023.pdf"
PDF = "India-National-Multidimentional-Poverty-Index-2023.pdf"
TABLE = "mpi2023_districts.tsv"
COLS = ["h_2016", "a_2016", "mpi_2016", "h_2021", "a_2021", "mpi_2021"]
NUM = re.compile(r"^(\d+\.\d+%|–|-|\d\.\d{3})$")


def visible_chars(page):
    big = [d["seqno"] for d in page.get_drawings() if d.get("fill") and d["rect"].width * d["rect"].height > 50000
           and d["rect"].y0 > 120]
    cut = max(big) if big else -1
    out = []
    for s in page.get_texttrace():
        if s["seqno"] < cut:
            continue
        for c in s["chars"]:
            out.append((round(c[2][1], 1), c[3][0], c[3][2], chr(c[0])))
    return out

def words(chars):
    lines = collections.defaultdict(list)
    for y, x0, x1, ch in chars:
        lines[round(y)].append((x0, x1, ch))
    res = []
    for y, cs in lines.items():
        cs.sort()
        w, last = "", None
        x_start = None
        for x0, x1, ch in cs:
            if last is not None and x0 - last > 6:
                res.append((y, x_start, w)); w = ""
            if not w:
                x_start = x0
            w += ch; last = x1
        if w:
            res.append((y, x_start, w))
    return res

def rows(page):
    ws = [(y, x, w.strip()) for y, x, w in words(visible_chars(page)) if w.strip()]
    raw = sorted((y, x, w) for y, x, w in ws if x < 185 and re.search("[A-Za-z]{2}", w))
    vals = [(y, x, w) for y, x, w in ws if x >= 185 and NUM.match(w)]
    has_vals = lambda y: any(abs(vy - y) <= 3 for vy, _, _ in vals)
    names = []  # a long name wraps onto a second line about 10pt below, with its values between: join the two
    for y, x, w in raw:
        if names and y - names[-1][3] < 13 and abs(x - names[-1][1]) < 3 and not has_vals(names[-1][3]) \
                and not has_vals(y):
            y0, x0, w0, _ = names[-1]
            names[-1] = ((y0 + y) / 2, x0, f"{w0.strip()} {w}", y)
        else:
            names.append((y, x, w, y))
    names = [(y, x, w) for y, x, w, _ in names]
    cols = collections.defaultdict(list)
    for y, x, w in vals:
        near = min(names, key=lambda n: abs(n[0] - y), default=None)
        if near is not None and abs(near[0] - y) <= 8:
            cols[near].append((x, w))
    out = []
    for n in sorted(cols):
        v = [w for x, w in sorted(cols[n])]
        if len(v) == 6:
            out.append({"name": unicodedata.normalize("NFKC", n[2]), "vals": v, "y": n[0]})
    return out


def extract(pdf_path):
    import warnings

    warnings.filterwarnings("ignore")
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("niti_mpi fetch needs PyMuPDF to read the report: pip install pymupdf") from exc
    doc = pymupdf.open(pdf_path)
    out = []
    for i, p in enumerate(doc):
        m = re.search(r"([A-Z][A-Za-z &]+?):\s*Overview of Districts?\b", p.get_text())
        if not m:
            continue
        for j in (i, i + 1):  # a long table runs on to the next page
            if j > i and (j >= len(doc) or re.search(r"Overview of Districts?\b", doc[j].get_text())):
                break
            for r in rows(doc[j]):
                out.append([m.group(1).strip(), j + 1, r["name"], *r["vals"]])
    return out


def _val(s):
    s = s.strip()
    if s in ("–", "-", ""):
        return None
    return round(float(s.rstrip("%")) / 100, 6) if s.endswith("%") else float(s)


class NitiMpi(Source):
    info = SourceInfo(
        id="niti_mpi",
        title="National Multidimensional Poverty Index: A Progress Review 2023 (district tables)",
        publisher="NITI Aayog, Government of India",
        homepage="https://www.niti.gov.in/whats-new/national-multidimensional-poverty-index-2023",
        license="Government of India publication (attribution: NITI Aayog)",
        description="Share of people who are multidimensionally poor (headcount ratio), the intensity of their "
        "deprivation and the MPI, for each of the 707 NFHS-5 districts, 2015-16 and 2019-21.",
        used_for=["Poverty lens (by district)", "District poverty facts"],
    )

    def fetch(self, force=False):
        dest = self.raw_dir / TABLE
        if dest.exists() and not force:
            return
        pdf = self.download(URL, PDF, force=force, expect_binary=True)
        rows = extract(pdf)
        with open(dest, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["state", "page", "district", *COLS])
            w.writerows(rows)
        core_fetch.record(self.id, TABLE, URL, note="district tables read from the PDF (visible layer only)")

    def process(self):
        out = []
        with open(self.raw_dir / TABLE, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                out.append({"state": r["state"], "district": r["district"], "page": int(r["page"]),
                            **{c: _val(r[c]) for c in COLS}})
        n5 = sum(1 for r in out if r["h_2021"] is not None)
        print(f"    {len(out)} district rows, {n5} with 2019-21 values, {len({r['state'] for r in out})} states/UTs")
        return {"vintage": "NITI Aayog National MPI 2023 (NFHS-5, 2019-21)", "_files": [TABLE], "districts": out}
