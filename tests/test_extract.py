"""Runs only when the RBC packages have been downloaded (make packages)."""
from pathlib import Path

import pytest

from src import config

PKG = config.DATA_RAW / "banks" / "packages" / "RY"
pytestmark = pytest.mark.skipif(not list(PKG.glob("*.xlsx")), reason="RBC packages not downloaded")


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
