"""Runs only when the BMO packages have been downloaded (make packages)."""
import pytest

from src import config
from src.extract import bmo

PKG = config.DATA_RAW / "banks" / "packages" / "BMO"


@pytest.mark.skipif(not list(PKG.glob("*.xlsx")), reason="BMO packages not downloaded")
def test_bmo_extract_reconciles():
    pcl, cap = bmo.extract(PKG)
    assert len(cap) == 35 and cap[["cet1_capital", "rwa", "cet1_ratio"]].notna().all().all()
    assert set(pcl["segment_label"]) == set(bmo.PRODUCTS)
    assert pcl[["pcl_total", "gross_loans"]].notna().all().all()

    def value(fy, fq, label, col):
        r = pcl[(pcl.fiscal_year == fy) & (pcl.fiscal_quarter == fq) & (pcl.segment_label == label)]
        return r[col].iloc[0]

    # Known values, FY2026 Q3 SFI p.31 (gross loans) and p.26 (Stage 3 PCL), Canada column
    assert value(2026, 3, "Credit cards", "gross_loans") == 10904
    assert value(2026, 3, "Residential mortgages", "pcl_impaired") == 30
    # FQ1 2018 comes from the FY2020 Q1 PDF: Canada gross loans, "by geographic area" table
    q1 = pcl[(pcl.fiscal_year == 2018) & (pcl.fiscal_quarter == 1)]
    assert q1["gross_loans"].sum() == pytest.approx(249145, abs=1)
    assert cap.iloc[0]["rwa"] == 270577
