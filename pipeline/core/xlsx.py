"""Minimal standard-library .xlsx reader (the pipeline is stdlib-only): sheet names, and rows as lists of str | float | None."""
import re, zipfile
import xml.etree.ElementTree as ET
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
def _col(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1
def sheets(path):
    with zipfile.ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        return [s.get("name") for s in wb.find("m:sheets", NS)]
def rows(path, sheet=None):
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = {r.get("Id"): r.get("Target") for r in rels}
        sh = wb.find("m:sheets", NS)
        pick = next((s for s in sh if sheet is None or s.get("name") == sheet))
        t = target[pick.get(f"{{{NS['r']}}}id")].lstrip("/")
        t = t if t.startswith("xl/") else "xl/" + t
        with z.open(t) as f:
            for _, el in ET.iterparse(f):
                if el.tag != f"{{{NS['m']}}}row":
                    continue
                out = []
                for c in el.findall("m:c", NS):
                    i = _col(c.get("r"))
                    while len(out) < i:
                        out.append(None)
                    v = c.find("m:v", NS)
                    typ = c.get("t")
                    if typ == "s" and v is not None:
                        val = shared[int(v.text)]
                    elif typ == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
                    elif v is None:
                        val = None
                    elif typ == "str":
                        val = v.text
                    else:
                        try:
                            val = float(v.text)
                        except ValueError:
                            val = v.text
                    out.append(val)
                el.clear()
                yield out
