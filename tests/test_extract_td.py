"""Runs only when the TD packages have been downloaded (make packages)."""
import pytest

from src import config
from src.extract import td

PKG = config.DATA_RAW / "banks" / "packages" / "TD"


@pytest.mark.skipif(not list(PKG.glob("TD_FY*")), reason="TD packages not downloaded")
def test_td_extract_reconciles():
    pcl, cap = td.extract(PKG)
    assert len(cap) == 35 and cap[["cet1_capital", "rwa", "cet1_ratio"]].notna().all().all()
    assert set(pcl["segment_label"]) == set(td.PRODUCTS)
    assert pcl[["pcl_total", "gross_loans"]].notna().all().all()
    gap = (cap["cet1_capital"] / cap["rwa"] - cap["cet1_ratio"]).abs()
    assert (gap < 0.0008).all()  # CET1 and RWA are disclosed in $bn to one decimal

    def value(y, q, label, col):
        r = pcl[(pcl.fiscal_year == y) & (pcl.fiscal_quarter == q) & (pcl.segment_label == label)]
        return r[col].iloc[0]

    # Known values: FQ3 2026 xlsx p.24 / p.36; FQ4 2021 from the FY2021 PDF p.21
    assert value(2026, 3, "Residential mortgages", "gross_loans") == 245012
    assert value(2026, 3, "Indirect auto", "pcl_impaired") == 112
    assert value(2021, 4, "Residential mortgages", "gross_loans") == 231675
