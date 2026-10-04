"""TD: Canadian PCL and loans by product, capital, earnings.

long-comment-ok: disclosure notes, same format as rbc.py / cibc.py
What TD's SFI discloses (xlsx FY2023+, PDF FY2018-FY2022; industry tables span 9 quarters):
  * Gross loans by product x geography -> gross_loans, direct (Canada column)
  * Stage 3 PCL by product x geography  -> pcl_impaired, direct
  * Stage 1-2 PCL only as a Canada total -> pcl_performing, ALLOCATED:
      personal vs business = Canada's Stage 1-2 allowance split (disclosed by geography)
      personal split       = each product's share of trailing-4Q Canadian Stage 3 PCL (as RBC, #17)
  * Capital, income before taxes, total PCL and common dividends from the highlights / equity pages
"""
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

BANK = "TD"
PERSONAL = {  # normalized label -> regex on the SFI label
    "Residential mortgages": r"^Residential mortgages",
    "HELOC": r"^HELOC",
    "Indirect auto": r"^Indirect auto",
    "Other personal": r"^Other$",
    "Credit card": r"^Credit card",
}
BUSINESS = "Business and government"
PRODUCTS = [*PERSONAL, BUSINESS]
NIL = {"–", "-", "—", "nil"}


@dataclass
class Row:
    label: str
    values: dict  # (fiscal_year, fiscal_quarter) -> float


def _num(c) -> float | None:
    if isinstance(c, bool) or c is None:
        return None
    if isinstance(c, (int, float)):
        return float(c)
    s = str(c).strip().replace(",", "").replace("$", "").strip()
    if s in NIL:
        return 0.0
    m = re.fullmatch(r"\(?(-?\d+(?:\.\d+)?)\)?", s)
    if not m:
        return None
    v = float(m.group(1))
    return -v if s.startswith("(") else v


def _quarter_columns(header_rows: list[tuple]) -> dict[int, tuple[int, int]]:
    """Map column -> (fiscal_year, quarter) from a year row above a Q1-Q4 row.

    Quarters run newest first; the year steps down whenever the quarter wraps Q1 -> Q4.
    """
    for i, r in enumerate(header_rows):
        qcols = [(j, int(str(c).strip()[1])) for j, c in enumerate(r)
                 if isinstance(c, str) and re.fullmatch(r"Q[1-4]", c.strip())]
        if len(qcols) < 3:
            continue
        years = [int(str(c).strip()) for rr in header_rows[max(i - 3, 0):i] for c in rr
                 if c is not None and re.fullmatch(r"20\d\d", str(c).strip())]
        year, prev, out = years[0], None, {}
        for j, q in qcols:
            if prev is not None and q > prev:
                year -= 1
            out[j], prev = (year, q), q
        return out
    return {}


def _sheet_rows(ws) -> tuple[str, list[Row]]:
    raw = list(ws.iter_rows(max_row=120, values_only=True))
    cols = _quarter_columns(raw[:10])
    title = " ".join(str(c) for r in raw[:2] for c in r if isinstance(c, str)).upper()
    rows = []
    for r in raw:
        label = next((str(c).strip() for c in r[:4] if isinstance(c, str) and c.strip()), "")
        label = re.sub(r"(\D)\d(,\d)*$", r"\1", label).strip()  # trailing footnote digits
        vals = {q: v for j, q in cols.items() if j < len(r) and (v := _num(r[j])) is not None}
        rows.append(Row(label, vals))
    return title, rows


ROW_RE = re.compile(r"^(?P<label>\S.*?)\s{2,}(?P<line>\d{1,3})\s+(?P<rest>.*)$")
TOKEN_RE = re.compile(r"\(?-?[\d,]+(?:\.\d+)?\)?|[–—]")


def _pdf_quarters(lines: list[str]) -> list[tuple[int, int]]:
    for i, ln in enumerate(lines[:12]):
        qs = re.findall(r"\bQ([1-4])\b", ln)
        if len(qs) >= 3:
            years = [int(y) for l in lines[max(i - 3, 0):i] for y in re.findall(r"\b(20\d\d)\b", l)]
            year, prev, out = years[0], None, []
            for q in map(int, qs):
                if prev is not None and q > prev:
                    year -= 1
                out.append((year, q))
                prev = q
            return out
    return []


def _pdf_page_rows(page: str) -> tuple[str, list[Row]]:
    lines = page.splitlines()
    title = " ".join(l.strip() for l in lines[:2]).upper()
    quarters = _pdf_quarters(lines)
    geo = any("Canada" in l and "Total" in l for l in lines[:12])
    width = 4 if geo else 1  # geography pages: Canada / U.S. / Int'l / Total per quarter
    rows = []
    for ln in lines:
        m = ROW_RE.match(ln.strip())
        if not m:
            rows.append(Row(ln.strip(), {}))
            continue
        nums = [_num(t) for t in TOKEN_RE.findall(m.group("rest").replace("$", " "))]
        nums = [v for v in nums if v is not None]
        vals = {q: nums[k * width] for k, q in enumerate(quarters) if k * width < len(nums)}
        label = re.sub(r"(\D)\d(,\d)*$", r"\1", m.group("label")).strip()
        rows.append(Row(label, vals))
    return title, rows


def load_pages(path: Path) -> list[tuple[str, list[Row]]]:
    """Every page / sheet as (upper-cased title, rows); values keyed by fiscal quarter."""
    if path.suffix == ".pdf":
        text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True,
                              text=True, check=True).stdout
        return [_pdf_page_rows(p) for p in text.split("\f") if p.strip()]
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return [_sheet_rows(ws) for ws in wb.worksheets]


def _pages(pages, title_prefix: str) -> list[list[Row]]:
    return [rows for t, rows in pages if t.startswith(title_prefix)]


def _first(rows: list[Row], pattern: str, start: int = 0) -> dict:
    rx = re.compile(pattern, re.I)
    return next((r.values for r in rows[start:] if r.values and rx.search(r.label)), {})


def _index(rows: list[Row], pattern: str) -> int | None:
    rx = re.compile(pattern, re.I)
    return next((i for i, r in enumerate(rows) if rx.search(r.label)), None)


def _collect(pages, title_prefix: str, pattern: str, after: str | None = None) -> dict:
    """One series from a table split across pages (each page holds different quarters)."""
    out = {}
    for rows in _pages(pages, title_prefix):
        start = _index(rows, after) if after else 0
        if start is None:
            continue
        for q, v in _first(rows, pattern, start).items():
            out.setdefault(q, v)
    return out


def parse_package(path: Path) -> dict:
    pages = load_pages(path)
    loans_t, pcl_t = "GROSS LOANS AND ACCEPTANCES BY INDUSTRY", "PROVISION FOR CREDIT LOSSES BY INDUSTRY"
    acl_t = "ALLOWANCE FOR CREDIT LOSSES BY INDUSTRY"
    s3_after = r"^Stage 3 provision|^Personal$"
    out = {
        "loans": {k: _collect(pages, loans_t, p) for k, p in PERSONAL.items()},
        "stage3": {k: _collect(pages, pcl_t, p) for k, p in PERSONAL.items()},
    }
    out["loans"][BUSINESS] = _collect(pages, loans_t, r"^Total business and government")
    out["stage3"][BUSINESS] = _collect(pages, pcl_t, r"^Total business and government")
    out["perf_ca"] = _collect(pages, pcl_t, r"^Personal, business and government")
    out["s12_acl_personal"] = _collect(pages, acl_t, r"^Personal$", after=r"^Stage 1 and Stage 2 allowance")
    out["s12_acl_business"] = _collect(pages, acl_t, r"^Business and Government$",
                                       after=r"^Stage 1 and Stage 2 allowance")

    hl = _pages(pages, "HIGHLIGHTS")
    hl = hl[0] if hl else []
    out["pcl_total"] = _first(hl, r"^Provision for (\(recovery of\) )?credit losses$")
    out["pretax"] = _first(hl, r"^Income (\(loss\) )?before provision for income taxes")
    out["cet1"] = {q: v * 1000 for q, v in _first(hl, r"^Common Equity Tier 1 Capital$").items()}
    out["ratio"] = {q: v / 100 for q, v in _first(hl, r"^Common Equity Tier 1 Capital ratio").items()}
    rwa = _first(hl, r"^Total risk-weighted assets") or _first(hl, r"^Common Equity Tier 1 Capital risk-weighted")
    out["rwa"] = {q: v * 1000 for q, v in rwa.items()}
    divs = _collect(pages, "ANALYSIS OF CHANGE IN EQUITY", r"^Common dividends$") or \
        _collect(pages, "ANALYSIS OF CHANGE IN EQUITY", r"^Common$", after=r"^Dividends$")
    out["divs"] = {q: abs(v) for q, v in divs.items()}
    return out


def _merge(parsed: list[dict], getter) -> dict:
    """Combine one series across packages; the newest package wins for each quarter."""
    out = {}
    for p in parsed:  # newest first
        for q, v in getter(p).items():
            out.setdefault(q, v)
    return out


def _sort_key(f: Path) -> tuple[int, int]:
    m = re.search(r"FY(\d{4})Q(\d)", f.name)
    return int(m.group(1)), int(m.group(2))


def extract(package_dir: Path, start=(2018, 1)) -> tuple[pd.DataFrame, pd.DataFrame]:
    files = sorted(list(package_dir.glob(f"{BANK}_FY*_SFI.xlsx")) + list(package_dir.glob(f"{BANK}_FY*_SFI.pdf")),
                   key=_sort_key, reverse=True)
    parsed = [parse_package(f) for f in files]
    src = {}
    for f, p in reversed(list(zip(files, parsed))):
        for q in p["ratio"]:
            src[q] = f.name

    def series(key, sub=None):
        return _merge(parsed, lambda p: p[key].get(sub, {}) if sub else p[key])

    loans = {k: series("loans", k) for k in PRODUCTS}
    stage3 = {k: series("stage3", k) for k in PRODUCTS}
    perf_ca, acl_p, acl_b = series("perf_ca"), series("s12_acl_personal"), series("s12_acl_business")
    end = max(series("ratio"))
    quarters = [q for q in sorted(perf_ca) if start <= q <= end]

    s3 = pd.DataFrame({k: stage3[k] for k in PERSONAL}).sort_index()
    weights = s3.clip(lower=0).rolling(4, min_periods=1).sum()
    weights = weights.div(weights.sum(axis=1), axis=0)

    rows = []
    for q in quarters:
        personal_share = acl_p[q] / (acl_p[q] + acl_b[q])
        for prod in PRODUCTS:
            if prod == BUSINESS:
                p_perf = perf_ca[q] * (1 - personal_share)
            else:
                p_perf = perf_ca[q] * personal_share * weights.loc[q, prod]
            p_imp = stage3[prod].get(q, np.nan)
            rows.append({
                "bank": BANK, "fiscal_year": q[0], "fiscal_quarter": q[1], "segment_label": prod,
                "pcl_total": round(p_perf + p_imp, 2), "pcl_performing": round(p_perf, 2),
                "pcl_impaired": p_imp, "gross_loans": loans[prod].get(q, np.nan), "source": src.get(q, ""),
                "notes": "Stage 3 + gross loans direct (Canada); Stage 1-2 allocated from Canada total",
            })
    pcl = pd.DataFrame(rows)

    cet1, ratio, rwa = series("cet1"), series("ratio"), series("rwa")
    pretax, pcl_tot, divs = series("pretax"), series("pcl_total"), series("divs")
    cap = pd.DataFrame([{
        "bank": BANK, "fiscal_year": q[0], "fiscal_quarter": q[1],
        "cet1_capital": cet1.get(q), "rwa": rwa.get(q), "cet1_ratio": ratio.get(q),
        "ppt_earnings": pretax[q] + pcl_tot[q], "pcl_total_bank": pcl_tot[q],
        "common_dividends": divs.get(q), "source": src.get(q, ""),
        "notes": "CET1 capital and RWA in $bn (1 decimal); RWA = CET1 capital RWA before FQ1 2019",
    } for q in quarters])
    return pcl, cap
