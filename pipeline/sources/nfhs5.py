"""NFHS-5 (2019-21) district fact sheets: housing, schooling, health and nutrition for India's 707 districts of 2017.

The fact sheets are published by IIPS (Mumbai) and the Ministry of Health and Family Welfare as one PDF per district;
the IIPS site was unreachable from the build machine, so the PDFs come from a public GitHub mirror of them, pinned to
one commit. Values are read from the PDFs themselves (not from the mirror's CSV, which has conversion errors), and on
every fetch a random sample of districts is checked value by value against the DHS Program's copies of the same fact
sheets (ICF, IIPS's survey partner): the result is recorded in the manifest and printed.

Reading PDFs needs `pdftotext` (poppler-utils), at fetch time only; the fetch writes one tab-separated table that
`process` reads with the standard library, as WorldCover's fetch needs rasterio.

Figures in parentheses are based on 25-49 unweighted cases (kept, flagged "small sample"); "*" means not shown (fewer
than 25 cases) and "na" not available: both are blank.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import shutil
import subprocess
import urllib.request

from ..core import fetch as core_fetch
from ..core.source import Source, SourceInfo

REPO = "SaiSiddhardhaKalla/NFHS"
COMMIT = "3403a17c5717fe08dc6414980965e5af83209411"
DHS = "https://www.dhsprogram.com/pubs/pdf/OF43/{st}_{name}.pdf"
TABLE = "nfhs5_district_factsheets.tsv"
NATIONAL = "https://www.dhsprogram.com/pubs/pdf/OF43/India_National_Fact_Sheet.pdf"
NATIONAL_TABLE = "nfhs5_india_factsheet.tsv"
COMPENDIUMS = ["https://dhsprogram.com/pubs/pdf/OF43/NFHS-5_India_and_State_Factsheet_Compendium_Phase-I.pdf",
               "https://dhsprogram.com/pubs/pdf/OF43/NFHS-5_India_and_State_Factsheet_Compendium_Phase-II.pdf"]
STATE_TABLE = "nfhs5_state_factsheets.tsv"
STATE_HEAD = re.compile(r"^\s*([A-Z][A-Za-z &]+?) - Key Indicators\s*$")
NAT_LINE = re.compile(r"^\s*(\d{1,3})\.\s+(.*?)\s{2,}((?:\(?[\d,]+(?:\.\d+)?\)?|\*|na)(?:\s+(?:\(?[\d,]+(?:\.\d+)?\)?|\*|na))*)\s*$")
VERIFY_N = 30

LINE = re.compile(r"^\s*(\d{1,3})\.\s+(.*?)\s{2,}(\(?[\d,]+(?:\.\d+)?\)?|\*|na|NA)"
                  r"(?:\s+(\(?[\d,]+(?:\.\d+)?\)?|\*|na|NA))?\s*$")
# State folders of the mirror -> 2011 census state code, and the DHS file prefix.
STATES = {
    "andaman_nicobar_island": ("35", "AN"), "andhra_pradesh": ("28", "AP"), "arunachal_pradesh": ("12", "AR"),
    "assam": ("18", "AS"), "bihar": ("10", "BR"), "chandigarh": ("04", "CH"), "chhattisgarh": ("22", "CT"),
    "dadra_nagar_haveli_daman_diu": ("26", "DD"), "nct_of_delhi": ("07", "DL"), "goa": ("30", "GA"),
    "gujarat": ("24", "GJ"), "haryana": ("06", "HR"), "himachal_pradesh": ("02", "HP"),
    "jammu_kashmir": ("01", "JK"), "jharkhand": ("20", "JH"), "karnataka": ("29", "KA"), "kerala": ("32", "KL"),
    "ladakh": ("37", "LH"), "lakshadweep": ("31", "LD"), "madhya_pradesh": ("23", "MP"),
    "maharashtra": ("27", "MH"), "manipur": ("14", "MN"), "meghalaya": ("17", "ML"), "mizoram": ("15", "MZ"),
    "nagaland": ("13", "NL"), "odisha": ("21", "OR"), "puducherry": ("34", "PY"), "punjab": ("03", "PB"),
    "rajasthan": ("08", "RJ"), "sikkim": ("11", "SK"), "tamil_nadu": ("33", "TN"), "telangana": ("36", "TG"),
    "tripura": ("16", "TR"), "uttar_pradesh": ("09", "UP"), "uttarakhand": ("05", "UT"),
    "west_bengal": ("19", "WB"),
}


def parse_pdf(path) -> dict[int, tuple[str, str]]:
    txt = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    title = ""
    m = re.search(r"District Fact Sheet\s+(.+?)\n", txt)
    if m:
        title = m.group(1).strip()
    out = {0: (title, "")}
    for line in txt.splitlines():
        mm = LINE.match(line)
        if mm and int(mm.group(1)) not in out:
            out[int(mm.group(1))] = (re.sub(r"\s+", " ", mm.group(2)).strip(), mm.group(3))
    return out


class Nfhs5(Source):
    info = SourceInfo(
        id="nfhs5",
        title="National Family Health Survey 2019-21 (NFHS-5): district fact sheets",
        publisher="International Institute for Population Sciences (IIPS) and Ministry of Health and Family "
        "Welfare; PDFs via a GitHub mirror, checked against the DHS Program's copies",
        homepage="https://rchiips.org/nfhs/districtfactsheet_NFHS-5.shtml",
        license="Government of India publication (attribution: IIPS and MoHFW, NFHS-5)",
        description="Key indicators for each of India's 707 districts (as of 31 March 2017): electricity, drinking "
        "water, sanitation, clean cooking fuel, health insurance, women's literacy and schooling, child marriage, "
        "institutional births, child stunting and underweight, anaemia. Read from the official fact sheet PDFs. "
        "Figures in parentheses in the fact sheets (25-49 cases) are flagged as small samples.",
        used_for=["District facts (housing, schooling, health, nutrition)", "NFHS-5 lenses"],
    )

    def _national(self, force):
        """India's fact sheet (columns: urban, rural, total, NFHS-4 total): the total, by indicator label."""
        dest = self.raw_dir / NATIONAL_TABLE
        if dest.exists() and not force:
            return
        pdf = self.download(NATIONAL, "India_National_Fact_Sheet.pdf", force=force, expect_binary=True)
        txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
        rows = []
        for line in txt.splitlines():
            m = NAT_LINE.match(line)
            if m:
                nums = m.group(3).split()
                total = nums[2] if len(nums) >= 3 else None
                rows.append([m.group(1), re.sub(r"\s+", " ", m.group(2)).strip(), total])
        with open(dest, "w", encoding="utf-8", newline="") as out:
            w = csv.writer(out, delimiter="\t")
            w.writerow(["n", "indicator", "total"])
            w.writerows(rows)
        core_fetch.record(self.id, NATIONAL_TABLE, NATIONAL, note="total column of the India fact sheet")

    def _states(self, force):
        """The India and state fact sheets in the two official compendiums: each state's total column."""
        dest = self.raw_dir / STATE_TABLE
        if dest.exists() and not force:
            return
        rows = []
        for k, url in enumerate(COMPENDIUMS, 1):
            pdf = self.download(url, f"compendium_phase{k}.pdf", force=force, expect_binary=True)
            txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
            state = None
            for line in txt.splitlines():
                h = STATE_HEAD.match(line)
                if h:
                    state = h.group(1).strip()
                    continue
                m = NAT_LINE.match(line)
                if state and m:
                    nums = m.group(3).split()
                    rows.append([state, m.group(1), re.sub(r"\s+", " ", m.group(2)).strip(),
                                 nums[2] if len(nums) >= 3 else None])
        with open(dest, "w", encoding="utf-8", newline="") as out:
            w = csv.writer(out, delimiter="\t")
            w.writerow(["state", "n", "indicator", "total"])
            w.writerows(rows)
        core_fetch.record(self.id, STATE_TABLE, " ; ".join(COMPENDIUMS), note="total column of each state fact sheet")

    def fetch(self, force=False):
        if shutil.which("pdftotext"):
            self._national(force)
            self._states(force)
        dest = self.raw_dir / TABLE
        if dest.exists() and not force:
            return
        if core_fetch.OFFLINE:
            raise core_fetch.OfflineError(f"--offline: {self.id}/{TABLE} is not cached")
        if not shutil.which("pdftotext") or not shutil.which("git"):
            raise SystemExit("nfhs5 fetch needs git and pdftotext (poppler-utils)")
        repo = self.raw_dir / "mirror"
        if not (repo / ".git").exists():
            repo.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout",
                            f"https://github.com/{REPO}", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "sparse-checkout", "set", "pdfs"], check=True)
            subprocess.run(["git", "-C", str(repo), "checkout", "-q", COMMIT], check=True)
        rows, files = [], []
        for folder in sorted((repo / "pdfs").iterdir()):
            if not folder.is_dir() or folder.name not in STATES:
                continue
            st, _dhs = STATES[folder.name]
            for f in sorted(folder.iterdir()):
                if not f.is_file() or f.name.startswith("."):
                    continue
                vals = parse_pdf(f)
                sha = hashlib.sha256(f.read_bytes()).hexdigest()
                files.append({"path": f"pdfs/{folder.name}/{f.name}", "sha256": sha})
                for n, (label, v) in sorted(vals.items()):
                    rows.append([st, folder.name, f.name, vals[0][0], n, label, v])
        with open(dest, "w", encoding="utf-8", newline="") as out:
            w = csv.writer(out, delimiter="\t")
            w.writerow(["state", "state_folder", "file", "title", "n", "indicator", "value"])
            w.writerows(rows)

        # Verify a random sample against the DHS Program's copies of the same fact sheets.
        rng = random.Random(COMMIT)
        sample = rng.sample(files, min(VERIFY_N, len(files)))
        checked = agree = differ = 0
        for item in sample:
            folder, name = item["path"].split("/")[1:3]
            dhs_name = "_".join(w.capitalize() for w in name.split("_"))
            url = DHS.format(st=STATES[folder][1], name=dhs_name)
            tmp = self.raw_dir / "verify.pdf"
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "indiaciv"}),
                                            timeout=60) as r, open(tmp, "wb") as o:
                    o.write(r.read())
                if tmp.read_bytes()[:4] != b"%PDF":
                    continue
            except Exception:
                continue
            ours = parse_pdf(repo / item["path"])
            theirs = parse_pdf(tmp)
            keys = [k for k in ours if k and k in theirs]
            if not keys:
                continue
            checked += 1
            if all(ours[k][1] == theirs[k][1] for k in keys):
                agree += 1
            else:
                differ += 1
        (self.raw_dir / "verify.pdf").unlink(missing_ok=True)
        note = (f"values read from {len(files)} fact-sheet PDFs at {REPO}@{COMMIT[:10]}; of {VERIFY_N} sampled "
                f"districts, {checked} were found on dhsprogram.com and {agree} matched value for value "
                f"({differ} differed)")
        print(f"    {note}")
        (self.raw_dir / "pdf_hashes.json").write_text(json.dumps(files, indent=0))
        core_fetch.record(self.id, TABLE, f"https://github.com/{REPO}/tree/{COMMIT}/pdfs", note=note,
                          verified_against="https://www.dhsprogram.com/pubs/pdf/OF43/", checked=checked,
                          matched=agree, differed=differ)

    def process(self):
        districts: dict[tuple, dict] = {}
        with open(self.raw_dir / TABLE, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                key = (r["state"], r["file"])
                d = districts.setdefault(key, {"state": r["state"], "file": r["file"], "title": r["title"],
                                                "values": {}, "small": [], "labels": {}})
                n = int(r["n"])
                if n == 0:
                    continue
                v = r["value"].strip()
                d["labels"][n] = r["indicator"]
                if v in ("*", "na", "NA", ""):
                    d["values"][n] = None
                    continue
                small = v.startswith("(")
                d["values"][n] = float(v.strip("()").replace(",", ""))
                if small:
                    d["small"].append(n)
        national = {}
        nat_path = self.raw_dir / NATIONAL_TABLE
        if nat_path.exists():
            with open(nat_path, encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f, delimiter="\t"):
                    v = (r["total"] or "").strip("()").replace(",", "")
                    national[r["indicator"]] = float(v) if re.fullmatch(r"\d+(\.\d+)?", v) else None
        states: dict[str, dict] = {}
        st_path = self.raw_dir / STATE_TABLE
        if st_path.exists():
            with open(st_path, encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f, delimiter="\t"):
                    v = (r["total"] or "").replace(",", "")
                    small = v.startswith("(")
                    v = v.strip("()")
                    d = states.setdefault(r["state"], {})
                    if r["indicator"] not in d:
                        d[r["indicator"]] = float(v) if re.fullmatch(r"\d+(\.\d+)?", v) else None
        print(f"    {len(districts)} district fact sheets; India fact sheet: {len(national)} indicators; "
              f"{len(states)} state fact sheets")
        return {"vintage": "NFHS-5 (2019-21) fact sheets", "_files": [TABLE, NATIONAL_TABLE, STATE_TABLE],
                "districts": list(districts.values()), "national": national, "states": states}
