"""BMO: Canadian PCL and loans by product, capital, earnings.

long-comment-ok: disclosure notes, same format as rbc.py / cibc.py
What BMO's SFI discloses (checked FY2020Q1-FY2026Q3 packages):
  * FQ4 2023 onward ("geography" pages): Stage 3 PCL and gross loans by Canada x product,
    direct; Stage 1-2 PCL only as a Canada total
  * Before FQ4 2023: product detail is total-bank only. Canada gives totals for gross loans,
    Stage 3 PCL and Stage 1-2 PCL -> ALLOCATED (decisions.md, BMO rows):
      consumer loans, Canada = Canadian P&C average loans by product x splice factor
                               (period-end Canada / Canadian P&C average, FQ4 2023-FQ3 2024);
                               restated P&C vintages are chain-linked (`_chain`)
      business loans, Canada = Canada total gross loans - consumer
      Stage 3, Canada        = total-bank product PCL x Canada loan share, scaled to the Canada total
  * Stage 1-2 PCL (all periods): Canada total split by each product's share of
    trailing-4Q Canadian Stage 3 PCL (as RBC, #17)
  * FQ1-FQ2 2018 are only in PDF packages: read from `pdftotext -layout` text (`_pdf_package`)
"""
import re
import subprocess
import warnings
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

from . import sfi

BANK = "BMO"
CONSUMER = {  # normalized label -> regex on the SFI label
    "Residential mortgages": r"^Residential mortgages$",
    "Consumer instalment and other personal": r"^Consumer instalment and other personal",
    "Credit cards": r"^Credit cards$",
}
BUSINESS = "Business and government"
PRODUCTS = [*CONSUMER, BUSINESS]
CPC_LOANS = {  # Canadian P&C "Average gross loans and acceptances: <x>"
    "Residential mortgages": r"^Average gross loans and acceptances: Residential mortgages",
    "Consumer instalment and other personal": r"^Average gross loans and acceptances: Consumer instalment",
    "Credit cards": r"^Average gross loans and acceptances: Credit cards",
}
GEO_Q = re.compile(r"^\s*Q([1-4])\s+(\d{4})\s*$")
Q_ONLY = re.compile(r"^\s*Q([1-4])\s*$")
YEAR = re.compile(r"^\s*(\d{4})\s*$")


def _label(r: tuple) -> str:
    lab = next((c for c in r[:2] if isinstance(c, str) and c.strip()), "")
    return sfi.clean_label(lab)


def _num(c) -> float | None:
    if isinstance(c, (int, float)) and not isinstance(c, bool):
        return float(c)
    return None


def _colmap(raw: list[tuple], geography: str) -> dict[int, tuple]:
    """Column -> (fiscal_year, fiscal_quarter) from BMO's two header styles.

    Geography pages: "Q3 2026" over Canada / U.S. / Other / Total; take the `geography` column.
    Other pages: a year row above a "Q4 Q3 ..." row.
    """
    for i, r in enumerate(raw[:8]):
        geo = {j: GEO_Q.match(c) for j, c in enumerate(r) if isinstance(c, str)}
        geo = {j: m for j, m in geo.items() if m}
        if len(geo) >= 2:
            sub = raw[i + 1]
            out = {}
            for j, m in geo.items():
                for k in range(j, min(j + 4, len(sub))):
                    if isinstance(sub[k], str) and sub[k].strip().lower().startswith(geography.lower()):
                        out[k] = (int(m.group(2)), int(m.group(1)))
                        break
            return out
        qs = {j: Q_ONLY.match(c) for j, c in enumerate(r) if isinstance(c, str)}
        qs = {j: m for j, m in qs.items() if m}
        if len(qs) >= 3 and i > 0:
            years = raw[i - 1]
            out = {}
            for j, m in qs.items():
                y = years[j] if j < len(years) else None
                y = int(y) if isinstance(y, (int, float)) else (int(YEAR.match(y).group(1))
                                                                if isinstance(y, str) and YEAR.match(y) else None)
                if y:
                    out.setdefault(j, (y, int(m.group(1))))
            # keep the first column of each quarter (later columns are YTD / mix)
            seen, keep = set(), {}
            for j in sorted(out):
                if out[j] not in seen:
                    seen.add(out[j])
                    keep[j] = out[j]
            return keep
    return {}


def _read_sheet(ws, geography: str = "Canada", max_rows: int = 120) -> sfi.Sheet:
    raw = list(ws.iter_rows(max_row=max_rows, values_only=True))
    cols = _colmap(raw, geography)
    rows = []
    for i, r in enumerate(raw, 1):
        vals = {q: v for j, q in cols.items() if j < len(r) and (v := _num(r[j])) is not None}
        rows.append(sfi.Row(i, _label(r), vals))
    head = " ".join(str(c) for r in raw[:6] for c in r if isinstance(c, str))
    return sfi.Sheet(ws.title, re.sub(r"\s+", " ", head.upper()), rows)


def _load(path: Path) -> list[sfi.Sheet]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return [_read_sheet(ws) for ws in wb.worksheets]


def _find(sheets: list[sfi.Sheet], title: str, pattern: str, start: int = 0) -> sfi.Row | None:
    for s in sfi.find_sheets(sheets, title):
        r = sfi.find_row(s, pattern, start=start)
        if r:
            return r
    return None


def _after(sheet: sfi.Sheet, header: str, pattern: str) -> dict:
    h = sfi.find_row(sheet, header, with_values=False)
    r = sfi.find_row(sheet, pattern, start=h.idx + 1) if h else None
    return r.values if r else {}


def _products(rows: list[sfi.Row]) -> dict[str, dict]:
    out = {}
    for name, pat in CONSUMER.items():
        r = next((r for r in rows if re.search(pat, r.label, re.I) and r.values), None)
        if r:
            out[name] = r.values
    r = next((r for r in rows if re.match(r"^Total Business and Government", r.label, re.I) and r.values), None)
    if r:
        out[BUSINESS] = r.values
    return out


def _merge_into(dst: dict, src: dict) -> None:
    for k, v in src.items():
        dst.setdefault(k, {}).update(v)


def parse_package(sheets: list[sfi.Sheet]) -> dict:
    out = {"geo_s3": {}, "geo_loans": {}, "geo_s12": {}, "geo_s3_total": {}}

    # FQ4 2023 onward: Canada columns of the product x geography pages
    for s in sfi.find_sheets(sheets, "GEOGRAPHY"):
        if "PROVISION FOR CREDIT LOSSES" in s.text:
            _merge_into(out["geo_s3"], _products(s.rows))
            perf = sfi.find_row(s, r"^Total provision for credit losses on performing")
            imp = sfi.find_row(s, r"^Total provision for credit losses on impaired")
            out["geo_s12"].update(perf.values if perf else {})
            out["geo_s3_total"].update(imp.values if imp else {})
        elif "GROSS LOANS" in s.text:
            _merge_into(out["geo_loans"], _products(s.rows))

    # Older layout: total-bank products plus Canada totals
    seg = next((s for s in sfi.find_sheets(sheets, "PROVISION FOR CREDIT LOSSES", "SEGMENTED")), None)
    if seg:
        out["s3_products"] = _products(sfi.section(seg, r"^Provision by Product", r"^Total Provision for Credit Losses$"))
        out["ca_s3"] = _after(seg, r"^Provision for Credit Losses on Impaired", r"^Canada$")
        out["ca_s12"] = _after(seg, r"^Provision for Credit Losses on Perform", r"^Canada$")
    geo = next((s for s in sfi.find_sheets(sheets, "BY GEOGRAPHIC AREA")), None)
    if geo:
        out["ca_loans"] = _after(geo, r"^Gross Loans and Acceptances$", r"^Canada$")
    gl = next((s for s in sfi.find_sheets(sheets, "GROSS LOANS AND ACCEPTANCES BY PRODUCT AND INDUSTRY")
               if "GEOGRAPHY" not in s.text), None)
    out["loans_products"] = _products(gl.rows) if gl else {}
    cpc = next((s for s in sfi.find_sheets(sheets, "CANADIAN P&C")), None)
    out["cpc_loans"] = {k: (sfi.find_row(cpc, p).values if cpc and sfi.find_row(cpc, p) else {})
                        for k, p in CPC_LOANS.items()}

    # Capital and earnings
    tb = next(s for s in sfi.find_sheets(sheets, "TOTAL BANK CONSOLIDATED"))
    out["pretax"] = sfi.find_row(tb, r"^Income before (income )?taxes$").values
    out["pcl_total"] = sfi.find_row(tb, r"^(Total )?provision for (\(recovery of\) )?credit losses$").values
    out["ratio"] = _find(sheets, "FINANCIAL HIGHLIGHTS", r"^Common Equity Tier 1 Ratio").values
    out["rwa"] = _find(sheets, "FINANCIAL HIGHLIGHTS", r"^CET1 capital (risk-weighted assets|RWA)").values
    out["divs"] = {q: abs(v) for q, v in
                   _find(sheets, "FINANCIAL HIGHLIGHTS", r"^Dividends on common shares").values.items()}
    return out


def _merge(parsed: list[dict], getter) -> dict:
    """Combine one series across packages; the newest package wins for each quarter."""
    out = {}
    for p in parsed:  # newest first
        for q, v in getter(p).items():
            out.setdefault(q, v)
    return out


def _chain(parsed: list[dict], getter) -> dict:
    """Like _merge, but rescale each older vintage to the newer one at their overlap (restatements)."""
    out = {}
    for p in parsed:  # newest first
        older = getter(p)
        overlap = [q for q in older if q in out and older[q]]
        f = np.mean([out[q] / older[q] for q in overlap]) if overlap else 1.0
        for q, v in older.items():
            out.setdefault(q, v * f)
    return out


def _packages(package_dir: Path) -> list[tuple[str, dict]]:
    """Parsed packages, newest first. PDFs only fill quarters no Excel package covers."""
    files = sorted(package_dir.glob(f"{BANK}_FY*_SFI.xlsx"), reverse=True)
    parsed = [(f.name, parse_package(_load(f))) for f in files]
    pdfs = sorted(package_dir.glob(f"{BANK}_FY*_SFI.pdf"), reverse=True)
    covered = {q for _, p in parsed for q in p["ratio"]}
    for f in pdfs:
        p = _pdf_package(f)
        if p and set(p["ratio"]) - covered:
            parsed.append((f.name, p))
            covered |= set(p["ratio"])
    return parsed


def extract(package_dir: Path, start=(2018, 1)) -> tuple[pd.DataFrame, pd.DataFrame]:
    named = _packages(package_dir)
    parsed = [p for _, p in named]
    src = {}
    for name, p in reversed(named):
        for q in p["ratio"]:
            src[q] = name

    def series(key, sub=None):
        return _merge(parsed, lambda p: p.get(key, {}).get(sub, {}) if sub else p.get(key, {}))

    geo_s3 = {k: series("geo_s3", k) for k in PRODUCTS}
    geo_loans = {k: series("geo_loans", k) for k in PRODUCTS}
    geo_s12 = series("geo_s12")
    s3_prod = {k: series("s3_products", k) for k in PRODUCTS}
    loans_prod = {k: series("loans_products", k) for k in PRODUCTS}
    cpc = {k: _chain(parsed, lambda p, k=k: p.get("cpc_loans", {}).get(k, {})) for k in CONSUMER}
    ca_s3, ca_s12, ca_loans = series("ca_s3"), series("ca_s12"), series("ca_loans")
    ratio = series("ratio")
    quarters = sorted(q for q in ratio if q >= start)
    direct = [q for q in quarters if all(q in geo_loans[k] for k in PRODUCTS)]

    # Splice: Canada period-end loans / Canadian P&C average loans, first 4 direct quarters
    splice = {k: np.mean([geo_loans[k][q] / cpc[k][q] for q in direct[:4]]) for k in CONSUMER}

    loans, s3 = {}, {}
    for q in quarters:
        if q in direct:
            loans[q] = {k: geo_loans[k][q] for k in PRODUCTS}
            s3[q] = {k: geo_s3[k][q] for k in PRODUCTS}
            continue
        cons = {k: cpc[k][q] * splice[k] for k in CONSUMER}
        loans[q] = {**cons, BUSINESS: ca_loans[q] - sum(cons.values())}
        est = {k: s3_prod[k][q] * loans[q][k] / loans_prod[k][q] for k in PRODUCTS}
        scale = ca_s3[q] / sum(est.values()) if abs(sum(est.values())) > 1e-9 else 0.0
        s3[q] = {k: est[k] * scale for k in PRODUCTS}

    s3_df = pd.DataFrame(s3).T.sort_index()
    weights = s3_df.clip(lower=0).rolling(4, min_periods=1).sum()
    weights = weights.div(weights.sum(axis=1), axis=0)

    rows = []
    for q in quarters:
        s12_ca = geo_s12[q] if q in direct else ca_s12[q]
        how = "direct" if q in direct else "allocated (pre-FQ4 2023)"
        for k in PRODUCTS:
            p_perf, p_imp = s12_ca * weights.loc[[q], k].iloc[0], s3[q][k]
            rows.append({
                "bank": BANK, "fiscal_year": q[0], "fiscal_quarter": q[1], "segment_label": k,
                "pcl_total": round(p_perf + p_imp, 2), "pcl_performing": round(p_perf, 2),
                "pcl_impaired": round(p_imp, 2), "gross_loans": round(loans[q][k], 1),
                "source": src.get(q, ""),
                "notes": f"Stage 3 + loans Canada {how}; Stage 1-2 allocated (decisions.md, BMO)",
            })
    pcl = pd.DataFrame(rows)

    rwa, pretax, pcl_tot, divs = series("rwa"), series("pretax"), series("pcl_total"), series("divs")
    cap = pd.DataFrame([{
        "bank": BANK, "fiscal_year": q[0], "fiscal_quarter": q[1],
        "cet1_capital": round(ratio[q] * rwa[q]), "rwa": rwa[q], "cet1_ratio": ratio[q],
        "ppt_earnings": pretax[q] + pcl_tot[q], "pcl_total_bank": pcl_tot[q],
        "common_dividends": divs.get(q), "source": src.get(q, ""),
        "notes": "CET1 capital = reported ratio (0.1%) x CET1 RWA",
    } for q in quarters])
    return pcl, cap


NUM = re.compile(r"\(?-?[\d,]*\.?\d+\)?(?:\s*%)?|(?<=\s)-(?=\s|$)")


def _pdf_value(tok: str) -> float:
    if tok == "-":
        return 0.0
    neg = tok.startswith("(")
    pct = tok.endswith("%")
    v = float(re.sub(r"[(),%\s]", "", tok))
    v = -v if neg else v
    return v / 100 if pct else v


def _pdf_sheets(path: Path) -> list[sfi.Sheet]:
    """Text-layout pages as sfi.Sheet: a "Q1 Q4 Q3 ..." line under a line of years sets the columns."""
    text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True,
                          text=True, check=True).stdout
    sheets = []
    for n, page in enumerate(text.split("\f"), 1):
        lines = page.splitlines()
        cols, has_line_no, rows, years = [], False, [], []
        for i, line in enumerate(lines, 1):
            qs = re.findall(r"(?<!\w)Q([1-4])(?!\w)", line)
            ys = re.findall(r"(?<!\d)(20\d{2})(?!\d)", line)
            if len(ys) >= 3 and not qs:
                years = [int(y) for y in ys]
            if len(qs) >= 3 and len(years) >= len(qs) - 2:
                cols = list(zip(years, [int(q) for q in qs]))
                seen = set()
                cols = [c if not (c in seen or seen.add(c)) else None for c in cols]
                has_line_no = has_line_no or "#" in line or "LINE" in " ".join(lines[max(0, i - 3):i])
                continue
            m = re.match(r"^\s*(\S.*?)\s{2,}(\S.*)$", line)
            label, rest = (m.group(1), m.group(2)) if m else (line.strip(), "")
            toks = [t.strip() for t in NUM.findall(" " + rest)]
            if has_line_no and toks and re.fullmatch(r"\d{1,3}", toks[0]):
                toks = toks[1:]
            vals = {}
            if cols and re.search(r"[A-Za-z]", label):
                for c, t in zip(cols, toks):
                    if c:
                        vals[c] = _pdf_value(t)
            rows.append(sfi.Row(i, sfi.clean_label(label), vals))
        head = " ".join(l.strip() for l in lines[:12] if l.strip())
        sheets.append(sfi.Sheet(f"pdf p{n}", re.sub(r"\s+", " ", head.upper()), rows))
    return sheets


def _pdf_package(path: Path) -> dict | None:
    try:
        return parse_package(_pdf_sheets(path))
    except (StopIteration, AttributeError, KeyError):
        return None
