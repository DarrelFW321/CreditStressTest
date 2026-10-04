"""Scotiabank: Canadian Banking PCL and loans by product, capital, earnings.

long-comment-ok: disclosure notes, same format as rbc.py / cibc.py
What Scotiabank's SFI discloses (checked FY2018-FY2026; FY2018-FY2020 are PDF only):
  * No loans or PCL by geography. The Canadian book is the Canadian Banking segment,
    which excludes International Banking and Global Banking and Markets (GBM).
  * Canadian Banking Retail / Commercial PCL, Stage 1-2 and Stage 3 -> direct
      business = Commercial (includes small business); GBM's Canadian corporate loans are out
  * Canadian Banking AVERAGE balances by product (mortgages, personal, cards, business) -> gross_loans
  * Retail PCL split across mortgages / personal / cards -> ALLOCATED (decisions.md, BNS):
      weight_p = total-bank trailing-4Q Stage 3 loss rate_p x Canadian Banking balance_p
"""
import re
import subprocess
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

BANK = "BNS"
RETAIL = {  # normalized label -> regex on the SFI label (Canadian Banking balances, type of borrower)
    "Residential mortgages": r"^Residential mortgages$",
    "Personal loans": r"^Personal loans$",
    "Credit cards": r"^Credit cards$",
}
BUSINESS = "Business and government"
PRODUCTS = [*RETAIL, BUSINESS]
RWA = r"^(CET1 capital risk-weighted assets|Capital risk-weighted assets)$"
MONTH_Q = {"jan": 1, "apr": 2, "jul": 3, "oct": 4}

NUM = re.compile(r"^\(?-?[\d,]*\.?\d+\)?$")


def _label(s: str) -> str:
    s = re.sub(r"⁽[⁰¹²³⁴⁵⁶⁷⁸⁹]+⁾", "", str(s))
    s = re.sub(r"\(\d+\)", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _num(tok) -> float | None:
    if isinstance(tok, (int, float)) and not isinstance(tok, bool):
        return float(tok)
    if not isinstance(tok, str):
        return None
    t = tok.strip()
    if t in ("-", "—", "–"):
        return 0.0
    if not NUM.match(t):
        return None
    neg = t.startswith("(") and t.endswith(")")
    v = float(t.strip("()").replace(",", ""))
    return -v if neg else v


def _quarter_token(s) -> tuple[int, int] | None:
    """'Q4/21', 'Q4 2021', '31-Oct-21', 'October 31, 2021' -> (fiscal_year, quarter)."""
    if not isinstance(s, str):
        return None
    s = s.strip()
    m = re.match(r"^Q([1-4])(?:\(\d\))?\s*[/ ]\s*(\d{2}|\d{4})(?:\(\d\))?$", s, re.I)
    if m:
        y = int(m.group(2))
        return (y + 2000 if y < 100 else y, int(m.group(1)))
    m = re.match(r"^\d{1,2}-([A-Za-z]{3})-(\d{2})$", s)
    if m and m.group(1).lower() in MONTH_Q:
        return (2000 + int(m.group(2)), MONTH_Q[m.group(1).lower()])
    m = re.match(r"^([A-Za-z]{3})[a-z]*\s+\d{1,2},\s*(\d{4})$", s)
    if m and m.group(1).lower() in MONTH_Q:
        return (int(m.group(2)), MONTH_Q[m.group(1).lower()])
    return None


def _bare_q(s) -> int | None:
    m = re.match(r"^Q([1-4])(?:\(\d\))?$", str(s).strip()) if isinstance(s, str) else None
    return int(m.group(1)) if m else None


def _year(s) -> int | None:
    if isinstance(s, (int, float)) and not isinstance(s, bool) and 2000 < s < 2100 and s == int(s):
        return int(s)
    m = re.match(r"^(20\d\d)(?:\(\d\))?$", s.strip()) if isinstance(s, str) else None
    if m:
        return int(m.group(1))
    return None


def _assign_years(qcols: list[tuple[int, int]], first_year: int) -> dict[int, tuple[int, int]]:
    """Bare 'Q4 Q3 Q2 Q1 Q4 ...' columns: the year steps down whenever the quarter number rises."""
    out, y, prev = {}, first_year, None
    for col, q in qcols:
        if prev is not None and q > prev:
            y -= 1
        out[col] = (y, q)
        prev = q
    return out


# ---------------------------------------------------------------- xlsx -------------------------
def _grid_header(raw: list[tuple]) -> tuple[int, dict[int, tuple[int, int]]]:
    """Row index of the quarter header and {column: (fiscal_year, quarter)}."""
    for i, r in enumerate(raw[:15]):
        full = {j: q for j, c in enumerate(r) if (q := _quarter_token(c))}
        if len(full) >= 3:
            return i, full
        bare = [(j, q) for j, c in enumerate(r) if (q := _bare_q(c))]
        if len(bare) >= 3:
            for k in range(i - 1, max(i - 4, -1), -1):
                years = [(j, y) for j, c in enumerate(raw[k]) if (y := _year(c))]
                if years:
                    return i, _assign_years(bare, min(years)[1])
    return -1, {}


def read_xlsx(path: Path) -> list[dict]:
    """Every sheet as {title, rows: [(label, {quarter: [values from the quarter column onward]})]}."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        raw = list(ws.iter_rows(max_row=200, values_only=True))
        head = " ".join(str(c) for r in raw[:10] for c in r if isinstance(c, str))
        hi, cols = _grid_header(raw)
        if not cols:
            continue
        first = min(cols)
        rows = []
        for r in raw[hi + 1:]:
            lab = next((c for c in r[:first] if isinstance(c, str) and c.strip()), "")
            vals = {q: [_num(c) for c in r[j:j + 3]] for j, q in cols.items() if j < len(r)}
            rows.append((_label(lab), vals))
        out.append({"title": re.sub(r"\s+", " ", head).upper(), "rows": rows})
    return out


# ---------------------------------------------------------------- pdf --------------------------
def _split_line(line: str) -> tuple[str, list[str]]:
    parts = re.split(r"\s{2,}", line.strip())
    if not parts or not parts[0]:
        return "", []
    if _num(parts[0].split()[0]) is not None:
        return "", [t for p in parts for t in p.split()]
    return parts[0], [t for p in parts[1:] for t in p.split()]


def read_pdf(path: Path) -> list[dict]:
    """Every page as {title, quarters: [...], rows: [(label, [numbers in order])]}."""
    text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True,
                          text=True, check=True).stdout
    out = []
    for page in text.split("\f"):
        lines = page.splitlines()
        head = " ".join(lines[:8]).upper()
        quarters, hi = [], -1
        for i, ln in enumerate(lines[:20]):
            toks = ln.split()
            full = [q for t in toks if (q := _quarter_token(t))]
            pairs = [_quarter_token(f"{a} {b}") for a, b in zip(toks, toks[1:])]
            pairs = [q for q in pairs if q]
            dates = [_quarter_token(t) for t in re.findall(r"[A-Z][a-z]+ \d{1,2}, \d{4}", ln)]
            for cand in (full, pairs, [d for d in dates if d]):
                if len(cand) >= 3:
                    quarters, hi = cand, i
                    break
            if quarters:
                break
            bare = [q for t in toks if (q := _bare_q(t))]
            if len(bare) >= 3:
                for k in range(i - 1, max(i - 4, -1), -1):
                    years = [y for t in lines[k].split() if (y := _year(t))]
                    if years:
                        quarters = list(_assign_years(list(enumerate(bare)), years[0]).values())
                        hi = i
                        break
                if quarters:
                    break
        if not quarters:
            continue
        rows = []
        for ln in lines[hi + 1:]:
            lab, toks = _split_line(ln)
            nums = [_num(t) for t in toks]
            if lab and nums and all(v is not None for v in nums):
                rows.append((_label(lab), nums))
        out.append({"title": head, "quarters": quarters, "rows": rows})
    return out


def _pdf_series(rows, quarters, pattern, stride=1, offset=0, nth=0, start=0) -> dict:
    hits = [(i, v) for i, (lab, v) in enumerate(rows) if i >= start and re.search(pattern, lab, re.I)]
    if len(hits) <= nth:
        return {}
    _, vals = hits[nth]
    return {q: vals[k * stride + offset] for k, q in enumerate(quarters) if k * stride + offset < len(vals)}


# ---------------------------------------------------------------- per package ------------------
def _xrow(sheet, pattern, offset=0, nth=0) -> dict:
    hits = [v for lab, v in sheet["rows"] if re.search(pattern, lab, re.I)
            and any(x[offset] is not None for x in v.values() if len(x) > offset)]
    if len(hits) <= nth:
        return {}
    return {q: x[offset] for q, x in hits[nth].items() if len(x) > offset and x[offset] is not None}


def _xsheet(sheets, *must):
    return next((s for s in sheets if all(m in s["title"] for m in must)), None)


PATTERNS = {
    "cb_bal": {k: v.replace("$", r"( & acceptances)?$") for k, v in RETAIL.items()}
    | {BUSINESS: r"^Business and government loans( & acceptances)?$"},
    "tb_loans": RETAIL,
    "tb_s3": RETAIL,
}


def parse_xlsx(path: Path) -> dict:
    sheets = read_xlsx(path)
    seg = _xsheet(sheets, "SEGMENT PERFORMANCE: CANADIAN BANKING")
    pcl_seg = _xsheet(sheets, "PROVISION FOR CREDIT LOSSES", "BY BUSINESS")
    pcl_type = _xsheet(sheets, "PROVISION FOR CREDIT LOSSES", "TYPE OF BORROWER")
    loans = _xsheet(sheets, "LOANS AND ACCEPTANCES BY TYPE OF BORROWER")
    inc = _xsheet(sheets, "CONSOLIDATED STATEMENT OF INCOME")
    cap = _xsheet(sheets, "REGULATORY CAPITAL HIGHLIGHTS")
    share = _xsheet(sheets, "COMMON SHARE AND OTHER INFORMATION")
    p = {
        "cb_bal": {k: _xrow(seg, pat) for k, pat in PATTERNS["cb_bal"].items()},
        "s12": {s: _xrow(pcl_seg, rf"^{s}$", 0) for s in ("Retail", "Commercial")},
        "s3": {s: _xrow(pcl_seg, rf"^{s}$", 1) for s in ("Retail", "Commercial")},
        "tb_s3": {k: _xrow(pcl_type, pat) for k, pat in RETAIL.items()},
        "tb_loans": {k: _xrow(loans, pat) for k, pat in RETAIL.items()},
        "pretax": _xrow(inc, r"^Income before taxes$"),
        "pcl_total": _xrow(inc, r"^Provision for credit losses$"),
        "cet1": _xrow(cap, r"^Common Equity Tier 1 capital$"),
        "rwa": _xrow(cap, RWA),
        "ratio": {q: v / 100 for q, v in _xrow(cap, r"^Common Equity Tier 1 \(as a percentage").items()},
        "divs": _xrow(share, r"^Common dividends paid"),
    }
    return p


def parse_pdf(path: Path) -> dict:
    pages = read_pdf(path)

    def page(*must):
        return next((pg for pg in pages if all(m in pg["title"] for m in must)), None)

    def series(pg, pattern, **kw):
        return _pdf_series(pg["rows"], pg["quarters"], pattern, **kw) if pg else {}

    seg = page("SEGMENT PERFORMANCE: CANADIAN BANKING")
    pcl_seg = page("PROVISION FOR CREDIT LOSSES BY BUSINESS LINE")
    pcl_type = page("PROVISION FOR CREDIT LOSSES BY TYPE OF BORROWER - IFRS 9") \
        or page("PROVISION FOR CREDIT LOSSES BY TYPE OF BORROWER")
    loans = page("LOANS AND ACCEPTANCES BY TYPE OF BORROWER")
    inc = page("CONSOLIDATED STATEMENT OF INCOME")
    cap = page("REGULATORY CAPITAL HIGHLIGHTS")
    share = page("COMMON SHARE AND OTHER INFORMATION")
    seg_neg = {q: -v for q, v in series(seg, r"^Provision for Credit Losses$").items()}  # shown as a cost
    p = {
        "cb_bal": {k: series(seg, pat) for k, pat in PATTERNS["cb_bal"].items()},
        "s12": {s: series(pcl_seg, rf"^{s}$", stride=6, offset=0) for s in ("Retail", "Commercial")},
        "s3": {s: series(pcl_seg, rf"^{s}$", stride=6, offset=1) for s in ("Retail", "Commercial")},
        "tb_s3": {k: series(pcl_type, pat) for k, pat in RETAIL.items()},
        "tb_loans": {k: series(loans, pat, stride=2) for k, pat in RETAIL.items()},
        "pretax": series(inc, r"^Income before Taxes$"),
        "pcl_total": series(inc, r"^Provision for Credit Losses$"),
        "cet1": series(cap, r"^Common Equity Tier 1 capital$"),
        "rwa": series(cap, RWA),
        "ratio": {q: v / 100 for q, v in series(cap, r"^Common Equity Tier 1 \(as a percentage").items()},
        "divs": series(share, r"^Common Dividends Paid"),
        "_seg_pcl": seg_neg,
    }
    return p


# ---------------------------------------------------------------- assemble ---------------------
def _merge(parsed: list[dict], getter) -> dict:
    """Combine one series across packages; the newest package wins for each quarter."""
    out = {}
    for p in parsed:  # newest first
        for q, v in getter(p).items():
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                out.setdefault(q, v)
    return out


def _package_key(f: Path) -> tuple[int, int]:
    m = re.search(r"FY(\d{4})Q(\d)", f.name)
    return int(m.group(1)), int(m.group(2))


def extract(package_dir: Path, start=(2018, 1)) -> tuple[pd.DataFrame, pd.DataFrame]:
    files = sorted((f for f in package_dir.glob(f"{BANK}_FY*_SFI.*") if f.suffix in (".xlsx", ".pdf")),
                   key=_package_key, reverse=True)
    parsed = [parse_xlsx(f) if f.suffix == ".xlsx" else parse_pdf(f) for f in files]
    src = {}
    for f, p in reversed(list(zip(files, parsed))):
        for q in p["cet1"]:
            src[q] = f.name

    def series(key, sub=None):
        return _merge(parsed, lambda p: p[key].get(sub, {}) if sub else p[key])

    bal = {k: series("cb_bal", k) for k in PRODUCTS}
    s12 = {s: series("s12", s) for s in ("Retail", "Commercial")}
    s3 = {s: series("s3", s) for s in ("Retail", "Commercial")}
    tb_s3 = pd.DataFrame({k: series("tb_s3", k) for k in RETAIL}).sort_index()
    tb_loans = pd.DataFrame({k: series("tb_loans", k) for k in RETAIL}).sort_index()
    quarters = sorted(q for q in s3["Retail"] if q >= start)

    # Retail split weights: total-bank trailing-4Q Stage 3 loss rate x Canadian Banking balance
    loss_rate = (tb_s3.clip(lower=0).rolling(4, min_periods=1).sum()
                 / tb_loans.reindex(tb_s3.index).ffill().bfill())
    cb = pd.DataFrame({k: bal[k] for k in RETAIL}).reindex(loss_rate.index)
    weights = loss_rate * cb
    weights = weights.div(weights.sum(axis=1), axis=0)

    rows = []
    for q in quarters:
        w = weights.loc[q]
        for prod in RETAIL:
            rows.append(_row(q, prod, s12["Retail"][q] * w[prod], s3["Retail"][q] * w[prod],
                             bal[prod].get(q, np.nan) * 1000, src))
        rows.append(_row(q, BUSINESS, s12["Commercial"][q], s3["Commercial"][q],
                         bal[BUSINESS].get(q, np.nan) * 1000, src))
    pcl = pd.DataFrame(rows)

    cet1, rwa, ratio = series("cet1"), series("rwa"), series("ratio")
    pretax, pcl_tot, divs = series("pretax"), series("pcl_total"), series("divs")
    cap = pd.DataFrame([{
        "bank": BANK, "fiscal_year": q[0], "fiscal_quarter": q[1],
        "cet1_capital": cet1.get(q), "rwa": rwa.get(q), "cet1_ratio": ratio.get(q),
        "ppt_earnings": round(pretax[q] + pcl_tot[q]), "pcl_total_bank": round(pcl_tot[q]),
        "common_dividends": round(abs(divs[q])) if q in divs else np.nan, "source": src.get(q, ""),
        "notes": "RWA = CET1 capital RWA; cet1_ratio as reported (0.1%)",
    } for q in quarters])
    return pcl, cap


def _row(q, prod, p_perf, p_imp, gross, src) -> dict:
    return {
        "bank": BANK, "fiscal_year": q[0], "fiscal_quarter": q[1], "segment_label": prod,
        "pcl_total": round(p_perf + p_imp, 2), "pcl_performing": round(p_perf, 2),
        "pcl_impaired": round(p_imp, 2), "gross_loans": round(gross, 1), "source": src.get(q, ""),
        "notes": "Canadian Banking segment; average balances; retail PCL split allocated (decisions.md, BNS)",
    }
