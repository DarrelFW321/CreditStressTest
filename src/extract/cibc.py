"""CIBC: Canadian PCL and loans by product, capital, earnings.

long-comment-ok: disclosure notes, same format as rbc.py

What CIBC's SFI discloses (checked FY2019-FY2026 packages; the FY2019 package
reaches back to FQ4 2017, so the FY2018 package is not needed):
  * Loans by geography x product, NET of allowance -> gross_loans = net + Canadian
    allowance added back (decisions.md #19)
  * Stage 3 PCL: consumer by product for the total bank, plus a Canada consumer
    total; business and government Canada total directly
      consumer product, Canada = product total x Canada share of consumer Stage 3 PCL
  * Stage 1-2 PCL only as total-bank Consumer / Business and government -> ALLOCATED:
      Canada share   = Canada's share of the Stage 1-2 allowance (disclosed by geography)
      consumer split = each product's share of trailing-4Q Canadian Stage 3 PCL (as RBC, #17)
  * CET1 capital is not in the SFI -> cet1_ratio x RWA (ratio rounded to 0.1%)
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import sfi

BANK = "CM"
CONSUMER = {  # normalized label -> regex on the SFI label
    "Residential mortgages": r"^Residential mortgages$",
    "Personal": r"^Personal$",
    "Credit card": r"^Credit cards?$",
}
BUSINESS = "Business and government"
CET1_RATIO = r"^(CET1|Common Equity Tier 1( \(CET1\))?) ratio( \(\d+\))?$"
PRODUCTS = [*CONSUMER, BUSINESS]


def _products(rows: list[sfi.Row]) -> dict[str, dict]:
    out = {}
    for name, pat in CONSUMER.items():
        r = next((r for r in rows if re.search(pat, r.label, re.I) and r.values), None)
        if r:
            out[name] = r.values
    return out


def _sheet_with(sheets, title: str, row_pattern: str) -> sfi.Sheet:
    return next(s for s in sfi.find_sheets(sheets, title) if sfi.find_row(s, row_pattern))


def parse_package(path: Path) -> dict:
    sheets = sfi.load(path, pct_strings=True)

    # PCL: Stage 3 by product (total bank), Stage 3 by geography, Stage 1-2 by portfolio
    pcl = next(s for s in sfi.find_sheets(sheets, "PROVISION FOR CREDIT LOSSES")
               if sfi.find_row(s, r"^Canada$") and sfi.find_row(s, r"stages 1 and", with_values=False))
    geo = sfi.find_row(pcl, r"^Canada$").idx  # first Canada row = consumer, by geography
    s3_products = _products(sfi.section(pcl, r"^Consumer$", r"^Total provision"))
    s3_consumer_total = sfi.find_row(pcl, r"^Total provision for credit losses - impaired loans, consumer").values
    s3_consumer_ca = sfi.find_row(pcl, r"^Canada$").values
    s3_business_ca = sfi.find_row(pcl, r"^Canada$", start=geo + 1).values
    s12 = sfi.find_row(pcl, r"stages 1 and", with_values=False).idx
    s12_consumer = sfi.find_row(pcl, r"^Consumer$", start=s12).values
    s12_business = sfi.find_row(pcl, r"^Business and government$", start=s12).values

    # Allowances: Stage 1-2 and Stage 3 by geography; Stage 3 consumer by product
    acl2 = next(s for s in sfi.find_sheets(sheets, "ALLOWANCE FOR CREDIT LOSSES")
                if sfi.find_row(s, r"^By geography", with_values=False)
                and sfi.find_row(s, r"^Stage 1 and 2 allowance", with_values=False))
    s3_hdr = sfi.find_row(acl2, r"^Stage 3 allowance", with_values=False).idx
    s12_hdr = sfi.find_row(acl2, r"^Stage 1 and 2 allowance", with_values=False).idx
    acl = {
        "s3_consumer_ca": sfi.find_row(acl2, r"^Canada$", start=s3_hdr).values,
        "s3_business_ca": _canada_after_n(acl2, s3_hdr, 2),
        "s12_consumer_ca": sfi.find_row(acl2, r"^Canada$", start=s12_hdr).values,
        "s12_business_ca": _canada_after_n(acl2, s12_hdr, 2),
        "s12_consumer": sfi.find_row(acl2, r"^Consumer loans$", start=s12_hdr).values,
        "s12_business": sfi.find_row(acl2, r"^Business and government loans$", start=s12_hdr).values,
    }
    acl_prod_sheet = next((s for s in sfi.find_sheets(sheets, "ALLOWANCE FOR CREDIT LOSSES")
                           if sfi.find_row(s, r"^Residential mortgages$")), None)
    s3_acl_products = _products(acl_prod_sheet.rows) if acl_prod_sheet else {}

    # Loans by geography: the Canada column (sfi maps each quarter to its first column)
    loans, loans_bg = {}, {}
    for s in sfi.find_sheets(sheets, "LOANS AND ACCEPTANCES"):
        if "CANADA" not in " ".join(r.label.upper() for r in s.rows[:8]) and "CANADA" not in s.text:
            continue
        for k, v in _products(s.rows).items():
            loans.setdefault(k, {}).update(v)
        bg = sfi.find_row(s, r"^Total net business and government loans")
        if bg:
            loans_bg.update(bg.values)

    # Capital and earnings
    fh = _sheet_with(sheets, "FINANCIAL HIGHLIGHTS", r"^Income before income taxes$")
    pretax = sfi.find_row(fh, r"^Income before income taxes$").values
    pcl_total = sfi.find_row(fh, r"^Provision for (\(reversal of\) )?credit losses$").values
    fh2 = _sheet_with(sheets, "FINANCIAL HIGHLIGHTS", CET1_RATIO)
    ratio = sfi.find_row(fh2, CET1_RATIO).values
    rwa = dict(sfi.find_row(fh2, r"^(Common Equity Tier 1 \(CET1\) capital RWA)$").values) \
        if sfi.find_row(fh2, r"^Common Equity Tier 1 \(CET1\) capital RWA$") else {}
    rwa.update(sfi.find_row(fh2, r"^Total (risk-weighted assets \(RWA\)|RWA)$").values)  # from FQ1 2019
    eq = _sheet_with(sheets, "CHANGES IN EQUITY", r"^Common$")
    divs_hdr = sfi.find_row(eq, r"^Dividends( and distributions)?$", with_values=False).idx
    divs = {q: -v for q, v in sfi.find_row(eq, r"^Common$", start=divs_hdr).values.items()}

    return dict(s3_products=s3_products, s3_consumer_total=s3_consumer_total,
                s3_consumer_ca=s3_consumer_ca, s3_business_ca=s3_business_ca,
                s12_consumer=s12_consumer, s12_business=s12_business, acl=acl,
                s3_acl_products=s3_acl_products, loans=loans, loans_bg=loans_bg,
                pretax=pretax, pcl_total=pcl_total, ratio=ratio, rwa=rwa, divs=divs)


def _canada_after_n(sheet: sfi.Sheet, start: int, n: int) -> dict:
    """The n-th `Canada` row after row `start` (1 = consumer, 2 = business and government)."""
    idx = start
    for _ in range(n):
        r = sfi.find_row(sheet, r"^Canada$", start=idx + 1)
        idx = r.idx
    return r.values


def _merge(parsed: list[dict], getter) -> dict:
    """Combine one series across packages; the newest package wins for each quarter."""
    out = {}
    for p in parsed:  # newest first
        for q, v in getter(p).items():
            out.setdefault(q, v)
    return out


def _share(num: float, den: float, fallback: float = 1.0) -> float:
    if den is None or num is None or np.isnan(den) or abs(den) < 1e-9:
        return fallback
    return float(np.clip(num / den, 0, 1))


def extract(package_dir: Path, start=(2018, 1)) -> tuple[pd.DataFrame, pd.DataFrame]:
    # FY2018's package has no geography x product loans table; FY2019 covers its quarters
    files = sorted((f for f in package_dir.glob(f"{BANK}_FY*_SFI.xlsx") if "FY2018" not in f.name),
                   reverse=True)
    parsed = [parse_package(f) for f in files]
    src = {}
    for f, p in reversed(list(zip(files, parsed))):
        for q in p["ratio"]:
            src[q] = f.name

    def series(key, sub=None):
        return _merge(parsed, lambda p: p[key].get(sub, {}) if sub else p[key])

    s3_prod = {k: series("s3_products", k) for k in CONSUMER}
    s3_tot, s3_ca, s3_bg_ca = series("s3_consumer_total"), series("s3_consumer_ca"), series("s3_business_ca")
    s12_c, s12_b = series("s12_consumer"), series("s12_business")
    acl = {k: series("acl", k) for k in parsed[0]["acl"]}
    s3_acl = {k: series("s3_acl_products", k) for k in CONSUMER}
    loans = {k: series("loans", k) for k in CONSUMER}
    loans_bg = series("loans_bg")
    quarters = sorted(q for q in s12_c if q >= start and q in loans_bg)

    # Canadian Stage 3 PCL by consumer product: total-bank product x Canada share
    s3_ca_prod = pd.DataFrame({
        k: {q: s3_prod[k].get(q, np.nan) * _share(s3_ca.get(q), s3_tot.get(q)) for q in s3_tot}
        for k in CONSUMER}).sort_index()
    weights = s3_ca_prod.clip(lower=0).rolling(4, min_periods=1).sum()
    weights = weights.div(weights.sum(axis=1), axis=0)

    rows = []
    for q in quarters:
        ca_c = _share(acl["s12_consumer_ca"].get(q), acl["s12_consumer"].get(q))
        ca_b = _share(acl["s12_business_ca"].get(q), acl["s12_business"].get(q))
        perf_c = s12_c[q] * ca_c
        w = weights.loc[q]
        # Gross-up: Stage 3 allowance split by product allowance (cards carry none),
        # Stage 1-2 allowance split like the Stage 1-2 PCL.
        s3a = {k: s3_acl[k].get(q, 0.0) for k in CONSUMER}
        s3a_tot = sum(s3a.values())
        for prod in CONSUMER:
            s3a_share = s3a[prod] / s3a_tot if s3a_tot else 0.0
            allowance = (acl["s3_consumer_ca"].get(q, 0.0) * s3a_share
                         + acl["s12_consumer_ca"].get(q, 0.0) * w[prod])
            p_perf, p_imp = perf_c * w[prod], s3_ca_prod.loc[q, prod]
            rows.append(_row(q, prod, p_perf, p_imp, loans[prod].get(q, np.nan) + allowance, src))
        bg_allow = acl["s3_business_ca"].get(q, 0.0) + acl["s12_business_ca"].get(q, 0.0)
        rows.append(_row(q, BUSINESS, s12_b[q] * ca_b, s3_bg_ca[q], loans_bg[q] + bg_allow, src))
    pcl = pd.DataFrame(rows)

    ratio, rwa = series("ratio"), series("rwa")
    pretax, pcl_tot, divs = series("pretax"), series("pcl_total"), series("divs")
    cap = pd.DataFrame([{
        "bank": BANK, "fiscal_year": q[0], "fiscal_quarter": q[1],
        "cet1_capital": round(ratio[q] * rwa[q]), "rwa": rwa[q], "cet1_ratio": ratio[q],
        "ppt_earnings": pretax[q] + pcl_tot[q], "pcl_total_bank": pcl_tot[q],
        "common_dividends": divs.get(q), "source": src.get(q, ""),
        "notes": "CET1 capital = reported ratio (0.1%) x RWA; RWA = CET1 capital RWA before FQ1 2019",
    } for q in quarters])
    return pcl, cap


def _row(q, prod, p_perf, p_imp, gross, src) -> dict:
    return {
        "bank": BANK, "fiscal_year": q[0], "fiscal_quarter": q[1], "segment_label": prod,
        "pcl_total": round(p_perf + p_imp, 2), "pcl_performing": round(p_perf, 2),
        "pcl_impaired": round(p_imp, 2), "gross_loans": round(gross, 1), "source": src.get(q, ""),
        "notes": "Loans Canada net + allowance; Stage 3 and Stage 1-2 partly allocated (decisions.md #19)",
    }
