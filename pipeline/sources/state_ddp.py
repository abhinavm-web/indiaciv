"""District Domestic Product as published by the states' own Directorates of Economics and Statistics.

India has no national district GDP series. 26 states / UTs compile District Domestic Product, each with its own
method (mostly by sharing the state's output among districts with indicators), so the figures are official but not
comparable across states, and each is shown with its state, measure, year and publication. Only states whose
publication could be downloaded from the build machine and read as a table are included; the rest are Pending.

Each state needs its own reader (the tables are laid out differently). Reading the PDFs needs `pdftotext`
(poppler-utils) and, for Telangana's map page, PyMuPDF, at fetch time only; the fetch writes one tab-separated table
that `process` reads with the standard library.
"""

from __future__ import annotations

import csv
import re
import subprocess

from ..core import fetch as core_fetch
from ..core.source import Source, SourceInfo

TABLE = "ddp_districts.tsv"
LAKH, CRORE = 1e5, 1e7


def _num(s):
    s = s.replace(",", "").strip().rstrip("*")
    try:
        return float(s)
    except ValueError:
        return None


def _text(path):
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout


def read_maharashtra(path):
    """Economic Survey of Maharashtra, Annexure 3.9: nominal GDDP (₹ crore), the 2022-23 column."""
    txt = _text(path)
    start = txt.index("NOMINAL GROSS DISTRICT DOMESTIC PRODUCT (AT CURRENT PRICES)")
    block = txt[start:start + 20000].split("\n")
    out = []
    for i, line in enumerate(block):
        m = re.match(r"^\s*(\d{1,2})\s+([A-Za-z][A-Za-z .$#-]*?)\s{2,}((?:[\d,]+\s+){11}[\d,]+)\s*$", line)
        if not m:
            continue
        name = m.group(2).replace("#", "").replace("$", "").strip()
        nxt = block[i + 1].strip() if i + 1 < len(block) else ""
        if nxt and re.fullmatch(r"[A-Za-z ]+", nxt) and not nxt.isupper():
            name = f"{name} {nxt}"  # "Chhatrapati" / "Sambhajinagar"
        vals = [_num(x) for x in m.group(3).split()]
        out.append((name, vals[1] * CRORE, "Mumbai city and Mumbai Suburban together" if "Mumbai" in name else
                    "Thane and Palghar together" if name == "Thane" else ""))
    return out


def read_tamil_nadu(path):
    """Statistical Handbook of Tamil Nadu, Table 34.4: NDDP at current prices (₹ lakh), 2022-23 (P)."""
    txt = _text(path)
    i = txt.index("34.4 DISTRICT INCOME ESTIMATES\n")
    block = txt[i:i + 8000].split("\n")
    out = []
    for line in block:
        if "CONSTANT" in line:
            break
        m = re.match(r"^\s*(\d{1,2})\s+([A-Za-z][A-Za-z .]*?)\s{2,}([\d\s]+)$", line)
        if m:
            vals = [_num(x) for x in m.group(3).split()]
            if vals:
                out.append((m.group(2).strip(), vals[-1] * LAKH, ""))
    return out


def read_uttarakhand(path):
    """Estimates of District Domestic Product of Uttarakhand: Table 1 of each district, GDDP at current prices
    (₹ lakh), the last column (2021-22, provisional)."""
    lines = _text(path).split("\n")
    out, name = [], None
    for i, line in enumerate(lines):
        if line.strip() == "Gross District Domestic Product at current prices":
            nxt = next((l for l in lines[i + 1:i + 4] if l.strip()), "")
            name = re.split(r"\s{2,}", nxt.strip())[0]
            if name.endswith("Mandal"):  # the two divisions' totals (Garhwal, Kumaon) follow the districts
                name = None
        elif name and "Gross District Domestic Product (12+13-14)" in line:
            vals = [_num(x) for x in line.split("(12+13-14)")[1].split()]
            out.append((name, vals[-1] * LAKH, ""))
            name = None
    return out


def read_telangana(path):
    """Telangana Economy (DES): the map page "Telangana Districts - GDDP 2022-23 (FRE)" at current prices (₹ crore),
    read from its district list (names and values in two columns, a long name wrapping onto a second line)."""
    import warnings

    warnings.filterwarnings("ignore")
    import pymupdf

    doc = pymupdf.open(path)
    page = next(p for p in doc if "Gross District Domestic Product" in p.get_text() and "Current Prices" in
                p.get_text() and "GDDP (Rs. Crores)" in p.get_text())
    words = page.get_text("words")
    head = next(w for w in words if w[4] == "GDDP" and w[1] > 90)
    vals = [(w[1], _num(w[4])) for w in words if w[0] >= head[0] + 25 and re.fullmatch(r"[\d,]+", w[4])]
    names = [w for w in words if head[0] - 70 <= w[0] < head[0] + 25 and w[1] > head[3] + 2 and
             re.match(r"[A-Za-z]", w[4]) and w[4] not in ("Note:", "Source:")]
    groups = {y: [] for y, _ in vals}
    for w in names:
        ys = sorted(groups, key=lambda y: (abs(y - w[1]), y > w[1]))  # nearest value; a tie goes to the one above
        if ys and abs(ys[0] - w[1]) <= 14:
            groups[ys[0]].append(w)
    out = []
    for y, v in vals:
        ws = sorted(groups[y], key=lambda w: (round(w[1]), w[0]))
        if ws:
            out.append((" ".join(w[4] for w in ws), v * CRORE, ""))
    return out


# state code -> publication
STATES = {
    "27": {"name": "Maharashtra", "publisher": "Directorate of Economics and Statistics, Maharashtra",
           "title": "Economic Survey of Maharashtra 2025-26, Annexure 3.9",
           "url": "https://mls.org.in/PDF2026/budjet/ESM_25_26_Eng%20Book.pdf", "file": "maharashtra_esm_2025-26.pdf",
           "measure": "Gross District Domestic Product", "year": "2022-23", "reader": read_maharashtra},
    "33": {"name": "Tamil Nadu", "publisher": "Department of Economics and Statistics, Tamil Nadu",
           "title": "Statistical Handbook of Tamil Nadu 2022-23, Table 34.4",
           "url": "https://des.tn.gov.in/sites/default/files/2025-07/34.%20STATE%20INCOME.pdf",
           "file": "tamil_nadu_handbook_state_income.pdf",
           "measure": "Net District Domestic Product", "year": "2022-23 (provisional)", "reader": read_tamil_nadu},
    "05": {"name": "Uttarakhand", "publisher": "Directorate of Economics and Statistics, Uttarakhand",
           "title": "Estimates of District Domestic Product of Uttarakhand, 2011-12 to 2021-22 (February 2023)",
           "url": "https://cdnbbsr.s3waas.gov.in/s3a9365bd906e11324065c35be476beb0c/uploads/2025/04/"
                  "202504171358549966.pdf", "file": "uttarakhand_ddp_2011-12_to_2021-22.pdf",
           "measure": "Gross District Domestic Product", "year": "2021-22 (provisional)", "reader": read_uttarakhand},
    "36": {"name": "Telangana", "publisher": "Directorate of Economics and Statistics, Telangana",
           "title": "Telangana Economy 2023-24 (PE)",
           "url": "https://des.telangana.gov.in/publications/TS%20Economy%20PE2023-24.pdf",
           "file": "telangana_economy_pe2023-24.pdf",
           "measure": "Gross District Domestic Product", "year": "2022-23 (first revised)", "reader": read_telangana},
}


class StateDdp(Source):
    info = SourceInfo(
        id="state_ddp",
        title="District Domestic Product, from the states' Directorates of Economics and Statistics",
        publisher="State Directorates of Economics and Statistics (Maharashtra, Tamil Nadu, Uttarakhand, Telangana)",
        homepage="https://www.mospi.gov.in/uploads/NssReports/Guideline%20for%20compilation%20of%20DDP%20estimates.pdf",
        license="Government publications (attribution: each state's DES)",
        description="Each state's own published district GDP (or net district product), at current prices, read "
        "from its official publication. Methods differ by state, so the figures are not comparable across states.",
        used_for=["District GDP (where the state publishes it)"],
    )

    def fetch(self, force=False):
        dest = self.raw_dir / TABLE
        if dest.exists() and not force:
            return
        rows = []
        for fips, s in STATES.items():
            path = self.download(s["url"], s["file"], force=force, expect_binary=True)
            got = s["reader"](path)
            print(f"    {s['name']}: {len(got)} districts")
            rows += [[fips, name, round(v), note] for name, v, note in got]
        with open(dest, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["state", "district", "value_rupees", "note"])
            w.writerows(rows)
        core_fetch.record(self.id, TABLE, " ; ".join(s["url"] for s in STATES.values()),
                          note="district tables read from each state's publication")

    def process(self):
        states = {f: {k: v for k, v in s.items() if k != "reader"} | {"districts": []} for f, s in STATES.items()}
        with open(self.raw_dir / TABLE, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                states[r["state"]]["districts"].append({"name": r["district"], "value": float(r["value_rupees"]),
                                                        "note": r["note"] or None})
        for s in states.values():
            print(f"    {s['name']}: {len(s['districts'])} districts, total ₹{sum(d['value'] for d in s['districts']) / 1e12:.2f} lakh crore")
        return {"vintage": "state DDP publications (latest available)", "_files": [TABLE], "states": states}
