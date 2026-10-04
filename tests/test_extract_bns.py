"""Runs only when the Scotiabank packages have been downloaded (make packages)."""
import pytest

from src import config

PKG = config.DATA_RAW / "banks" / "packages" / "BNS"


@pytest.mark.skipif(not list(PKG.glob("BNS_FY*")), reason="Scotiabank packages not downloaded")
def test_bns_extract_reconciles():
    from src.extract import bns
    pcl, cap = bns.extract(PKG)
    assert len(cap) == 35 and cap[["cet1_capital", "rwa", "cet1_ratio"]].notna().all().all()
    assert ((cap["cet1_capital"] / cap["rwa"] - cap["cet1_ratio"]).abs() < 0.0005).all()
    assert set(pcl["segment_label"]) == set(bns.PRODUCTS)
    assert pcl[["pcl_total", "gross_loans"]].notna().all().all()
    q = pcl[(pcl.fiscal_year == 2026) & (pcl.fiscal_quarter == 3)].set_index("segment_label")
    # Known values, FQ3 2026 SFI: Canadian Banking Retail Stage 3 PCL 345, Commercial 8 + 121 (p.23);
    # average credit card balance $9.7bn (p.4); CET1 capital 64,508 (p.26)
    assert q.loc[list(bns.RETAIL), "pcl_impaired"].sum() == pytest.approx(345, abs=0.05)
    assert q.loc["Business and government", "pcl_total"] == 129
    assert q.loc["Credit cards", "gross_loans"] == 9700
    assert cap.set_index(["fiscal_year", "fiscal_quarter"]).loc[(2026, 3), "cet1_capital"] == 64508
    # PDF era: FQ2 2020 Canadian Banking Retail Stage 1-2 / Stage 3 = 272 / 255 (FY2020 SFI p.22)
    q = pcl[(pcl.fiscal_year == 2020) & (pcl.fiscal_quarter == 2) & pcl.segment_label.isin(bns.RETAIL)]
    assert q["pcl_performing"].sum() == pytest.approx(272, abs=0.05)
    assert q["pcl_impaired"].sum() == pytest.approx(255, abs=0.05)
