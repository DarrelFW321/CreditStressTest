"""Runs only when the bank packages have been downloaded (make packages)."""
from pathlib import Path

import pytest

from src import config

PKG = config.DATA_RAW / "banks" / "packages" / "RY"

@pytest.mark.skipif(not list(PKG.glob("*.xlsx")), reason="RBC packages not downloaded")
def test_rbc_extract_reconciles():
    from src.extract import rbc
    pcl, cap = rbc.extract(PKG)
    assert len(cap) >= 35 and cap["cet1_capital"].notna().all() and cap["rwa"].notna().all()
    assert set(pcl["segment_label"]) == set(rbc.PRODUCTS)
    # Canadian PCL is a subset of total-bank PCL (checked in build quarters; in the
    # 2021-22 releases foreign books released more, so the inequality flips)
    canada = pcl.groupby(["fiscal_year", "fiscal_quarter"])["pcl_total"].sum()
    total = cap.set_index(["fiscal_year", "fiscal_quarter"])["pcl_total_bank"].loc[canada.index]
    build = total > 0
    assert (canada[build] <= total[build] + 25).mean() > 0.9  # FQ1 2021: Canada built, abroad released
    # Known value: FQ4 2025 Canadian residential mortgages, SFI page 21
    row = pcl[(pcl.fiscal_year == 2025) & (pcl.fiscal_quarter == 4) & (pcl.segment_label == "Residential mortgages")]
    assert row["gross_loans"].iloc[0] == 454346


CM_PKG = config.DATA_RAW / "banks" / "packages" / "CM"


@pytest.mark.skipif(not list(CM_PKG.glob("*.xlsx")), reason="CIBC packages not downloaded")
def test_cibc_extract_reconciles():
    from src.extract import cibc
    pcl, cap = cibc.extract(CM_PKG)
    assert len(cap) >= 35 and cap[["cet1_capital", "rwa", "cet1_ratio"]].notna().all().all()
    assert set(pcl["segment_label"]) == set(cibc.PRODUCTS)
    assert pcl[["pcl_total", "gross_loans"]].notna().all().all()
    # Known value: FQ3 2026 Canadian business and government, SFI p.23 net 120,177
    # + Canadian Stage 3 (505) and Stage 1-2 (357) allowance, p.28
    row = pcl[(pcl.fiscal_year == 2026) & (pcl.fiscal_quarter == 3) & (pcl.segment_label == "Business and government")]
    assert row["gross_loans"].iloc[0] == 121039
    # Canadian PCL is a subset of total-bank PCL in quarters with a build
    canada = pcl.groupby(["fiscal_year", "fiscal_quarter"])["pcl_total"].sum()
    total = cap.set_index(["fiscal_year", "fiscal_quarter"])["pcl_total_bank"].loc[canada.index]
    build = total > 0
    assert (canada[build] <= total[build] + 25).mean() > 0.9
