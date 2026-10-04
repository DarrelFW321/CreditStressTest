"""RBC: Canadian PCL and loans by product, capital, earnings.

What RBC's SFI discloses (checked FY2018-FY2026 packages):
  * Stage 3 PCL by geography x product (Canada: mortgages, HELOC, other personal,
    cards, small business, wholesale)  -> pcl_impaired, direct
  * Stage 1-2 PCL only as total-bank Retail and Wholesale  -> pcl_performing, ALLOCATED:
      Canada share   = Canadian loans / total loans, separately for retail and wholesale
      retail split   = each retail product's share of trailing-4Q Canadian Stage 3 PCL
      wholesale      = all to Wholesale (Canadian small business stays retail-allocated)
  * Loans by geography x product -> gross_loans, direct
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import sfi

BANK = "RY"
PRODUCTS = {  # normalized label -> regex on the SFI label
    "Residential mortgages": r"^Residential mortgages$",
    "HELOC": r"^HELOC$",
    "Other personal": r"^(Other personal|Personal)$",
    "Credit cards": r"^Credit cards?$",
    "Small business": r"^Small business$",
    "Wholesale": r"^Wholesale$",
}
RETAIL = ["Residential mortgages", "HELOC", "Other personal", "Credit cards", "Small business"]


def _products(rows: list[sfi.Row]) -> dict[str, dict]:
    out = {}
    for name, pat in PRODUCTS.items():
        r = next((r for r in rows if re.search(pat, r.label, re.I) and r.values), None)
        if r:
            out[name] = r.values
    return out


def parse_package(path: Path) -> dict:
    sheets = sfi.load(path)
    pcl_sheets = sfi.find_sheets(sheets, "PROVISION FOR CREDIT LOSSES")

    # Stage 3 PCL, Canada, by product
    s3 = next(s for s in pcl_sheets if sfi.find_row(s, r"by geography", with_values=False))
    stage3 = _products(sfi.section(s3, r"^Canada$", r"^(Total Canada|Canada - Total|United States)"))

    # Stage 1-2 PCL, total bank, retail / wholesale
    main = next(s for s in pcl_sheets if sfi.find_row(s, r"^PCL on performing loans"))
    end = sfi.find_row(main, r"^PCL on performing loans").idx
    perf = {"Retail": sfi.find_row(main, r"^Retail$", end=end).values,
            "Wholesale": sfi.find_row(main, r"^Wholesale$", end=end).values}

    # Loans by geography
    ln = next(s for s in sfi.find_sheets(sheets, "LOANS AND ACCEPTANCES")
              if sfi.find_row(s, r"^United States", with_values=False))
    canada_rows = sfi.section(ln, r"^Canada$", r"^United States")
    loans = _products(canada_rows)
    geo_totals = {"Retail": {}, "Wholesale": {}}
    for start, stop in [(r"^Canada$", r"^United States"), (r"^United States", r"^Other International"),
                        (r"^Other International", r"^Total")]:
        rows = sfi.section(ln, start, stop)
        for seg in geo_totals:
            r = next((r for r in rows if r.label == seg and r.values), None)
            for q, v in (r.values if r else {}).items():
                geo_totals[seg][q] = geo_totals[seg].get(q, 0.0) + v
    canada_seg = {seg: next(r.values for r in canada_rows if r.label == seg and r.values)
                  for seg in geo_totals}

    # Capital and earnings
    hl = next(s for s in sheets if sfi.find_row(s, r"Common Equity Tier 1 \(CET1\) capital ratio"))
    cet1_ratio = sfi.find_row(hl, r"Common Equity Tier 1 \(CET1\) capital ratio").values
    rwa_row = next(sfi.find_row(s, r"^Total (capital )?RWA \(\$ billions\)") for s in sheets
                   if sfi.find_row(s, r"^Total (capital )?RWA \(\$ billions\)"))
    rwa = {q: v * 1000 for q, v in rwa_row.values.items()}
    flow = sfi.find_sheets(sheets, "FLOW STATEMENT OF THE MOVEMENTS IN REGULATORY CAPITAL")[0]
    cet1 = sfi.find_row(flow, r"^Closing amount").values
    inc = next(s for s in sheets if sfi.find_row(s, r"^Income before income taxes$"))
    pretax = sfi.find_row(inc, r"^Income before income taxes$").values
    pcl_total = sfi.find_row(inc, r"^Provision for credit losses$").values
    divs = next(sfi.find_row(s, r"^Common dividends$").values for s in sheets
                if sfi.find_row(s, r"^Common dividends$"))

    return dict(stage3=stage3, perf=perf, loans=loans, geo_totals=geo_totals, canada_seg=canada_seg,
                cet1_ratio=cet1_ratio, rwa=rwa, cet1=cet1, pretax=pretax, pcl_total=pcl_total, divs=divs)


def _merge(parsed: list[tuple[str, dict]], getter) -> dict:
    """Combine one series across packages; the newest package wins for each quarter."""
    out = {}
    for _, p in parsed:  # newest first
        for q, v in getter(p).items():
            out.setdefault(q, v)
    return out


def extract(package_dir: Path, start=(2018, 1)) -> tuple[pd.DataFrame, pd.DataFrame]:
    files = sorted(package_dir.glob(f"{BANK}_FY*_SFI.xlsx"), reverse=True)
    parsed = [(f.name, parse_package(f)) for f in files]
    src = {}
    for name, p in reversed(parsed):  # record newest source per quarter
        for q in p["cet1_ratio"]:
            src[q] = name

    def series(*keys):
        return _merge(parsed, lambda p: p[keys[0]].get(keys[1], {}) if len(keys) > 1 else p[keys[0]])

    stage3 = {k: series("stage3", k) for k in PRODUCTS}
    loans = {k: series("loans", k) for k in PRODUCTS}
    perf = {k: series("perf", k) for k in ("Retail", "Wholesale")}
    geo_tot = {k: series("geo_totals", k) for k in ("Retail", "Wholesale")}
    ca_seg = {k: series("canada_seg", k) for k in ("Retail", "Wholesale")}
    quarters = sorted(q for q in perf["Retail"] if q >= start)

    s3 = pd.DataFrame(stage3).sort_index()
    weights = s3[RETAIL].clip(lower=0).rolling(4, min_periods=1).sum()
    weights = weights.div(weights.sum(axis=1), axis=0)

    rows = []
    for q in quarters:
        ca_share = {k: ca_seg[k][q] / geo_tot[k][q] for k in ("Retail", "Wholesale")}
        retail_perf_ca = perf["Retail"][q] * ca_share["Retail"]
        for prod in PRODUCTS:
            if prod == "Wholesale":
                p_perf = perf["Wholesale"][q] * ca_share["Wholesale"]
            else:
                p_perf = retail_perf_ca * weights.loc[[q], prod].iloc[0]
            p_imp = stage3[prod].get(q, np.nan)
            rows.append({
                "bank": BANK, "fiscal_year": q[0], "fiscal_quarter": q[1], "segment_label": prod,
                "pcl_total": round(p_perf + p_imp, 2), "pcl_performing": round(p_perf, 2),
                "pcl_impaired": p_imp, "gross_loans": loans[prod].get(q, np.nan),
                "source": src.get(q, ""),
                "notes": "Stage 3 + loans direct (Canada); Stage 1-2 allocated (decisions.md #17)",
            })
    pcl = pd.DataFrame(rows)

    cet1, ratio, rwa = series("cet1"), series("cet1_ratio"), series("rwa")
    pretax, pcl_tot, divs = series("pretax"), series("pcl_total"), series("divs")
    cap = pd.DataFrame([{
        "bank": BANK, "fiscal_year": q[0], "fiscal_quarter": q[1],
        "cet1_capital": cet1.get(q), "rwa": rwa.get(q),
        "cet1_ratio": ratio.get(q), "ppt_earnings": pretax[q] + pcl_tot[q], "pcl_total_bank": pcl_tot[q],
        "common_dividends": divs.get(q), "source": src.get(q, ""),
        "notes": "RWA = total capital RWA ($bn, 1 decimal); cet1_ratio as reported (rounded to 0.1%)",
    } for q in quarters])
    return pcl, cap
