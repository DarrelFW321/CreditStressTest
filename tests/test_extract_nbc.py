"""Runs only when the National Bank packages have been downloaded (make packages)."""
import pytest

from src import config
from src.extract import nbc

PKG = config.DATA_RAW / "banks" / "packages" / "NBC"


@pytest.mark.skipif(not list(PKG.glob("*_REGCAP.xlsx")), reason="NBC packages not downloaded")
def test_nbc_extract_reconciles():
    pcl, cap = nbc.extract(PKG)
    assert len(cap) == 35 and cap[["cet1_capital", "rwa", "cet1_ratio"]].notna().all().all()
    assert set(pcl["segment_label"]) == set(nbc.PRODUCTS)
    assert pcl[["pcl_total", "gross_loans"]].notna().all().all()
    assert ((cap["cet1_capital"] / cap["rwa"] - cap["cet1_ratio"]).abs() <= 0.0005).all()
    # Known values, FQ3 2026: Canadian residential mortgages (SFI p.28) and CET1 / RWA (CC1)
    row = pcl[(pcl.fiscal_year == 2026) & (pcl.fiscal_quarter == 3)
              & (pcl.segment_label == "Residential mortgages")]
    assert row["gross_loans"].iloc[0] == 123526
    c = cap[(cap.fiscal_year == 2026) & (cap.fiscal_quarter == 3)].iloc[0]
    assert (c.cet1_capital, c.rwa) == (26859, 198746)
