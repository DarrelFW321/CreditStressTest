"""Synthetic data with known parameters, so the pipeline can be tested before
any real bank figures are collected. Nothing here is real bank data."""
import numpy as np
import pandas as pd
import pytest

from src import config
from src.load_banks import build_capital, build_panel
from src.load_macro import add_features

TRUE_BETA = {"d_unemp_l1": 40.0, "gdp_yoy": -3.0, "hpi_yoy_l2": -1.0, "rate_l2": 2.0}
TRUE_RHO = 0.5
BASE_BPS = {"mortgage": 3.0, "consumer": 120.0, "business": 25.0}
LOANS = {"mortgage": 300_000.0, "consumer": 80_000.0, "business": 150_000.0}


@pytest.fixture(scope="session")
def macro() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    q = pd.period_range("2010Q1", "2026Q2", freq="Q")
    n = len(q)
    unemp = 6.5 + rng.normal(0, 0.15, n).cumsum() * 0.3
    covid = (q >= pd.Period("2020Q2")) & (q <= pd.Period("2021Q2"))
    unemp[covid] += np.linspace(6, 1, covid.sum())
    gdp = 2_000_000 * np.cumprod(1 + rng.normal(0.004, 0.003, n))
    gdp[q == pd.Period("2020Q2")] *= 0.88
    hpi = 150 * np.cumprod(1 + rng.normal(0.01, 0.02, n))
    rate = np.clip(1.5 + rng.normal(0, 0.25, n).cumsum(), 0.25, 5.0)
    levels = pd.DataFrame({"unemp": unemp, "gdp": gdp, "hpi": hpi, "policy_rate": rate}, index=q)
    return add_features(levels)


@pytest.fixture(scope="session")
def raw_bank_data(macro):
    """Raw rows in the hand-collected format, using bank-style labels."""
    rng = np.random.default_rng(1)
    mapping = pd.read_csv(config.ROOT / "data" / "portfolio_map.csv")
    rows, cap_rows = [], []
    for i, bank in enumerate(config.BANKS):
        labels = mapping[mapping["bank"] == bank]
        for p in config.PORTFOLIOS:
            lab = labels[labels["portfolio"] == p]["segment_label"].tolist()
            alpha = BASE_BPS[p] * (1 + 0.1 * i)
            lag = alpha / (1 - TRUE_RHO)
            for fy in range(2018, 2027):
                for fq in range(1, 5):
                    if (fy, fq) > (2026, 3):
                        break
                    cq = pd.Period(f"{fy - 1}Q4", "Q") + (fq - 1)
                    x = macro.loc[cq]
                    bps = alpha + sum(TRUE_BETA[k] * x[k] for k in TRUE_BETA)\
                        + TRUE_RHO * lag + rng.normal(0, 2)
                    lag = bps
                    loans = LOANS[p] * (1 + 0.01 * i) * (1.01 ** (fy - 2018))
                    for j, label in enumerate(lab):  # split across the bank's labels
                        share = 1 / len(lab)
                        rows.append({"bank": bank, "fiscal_year": fy, "fiscal_quarter": fq,
                                     "segment_label": label, "pcl_total": bps / 4 / 1e4 * loans * share,
                                     "gross_loans": loans * share})
        for fy in range(2018, 2027):
            for fq in range(1, 5):
                if (fy, fq) > (2026, 3):
                    break
                cap_rows.append({"bank": bank, "fiscal_year": fy, "fiscal_quarter": fq,
                                 "cet1_capital": 60_000 + 500 * i, "rwa": 450_000 + 2_000 * i,
                                 "ppt_earnings": 5_000, "pcl_total_bank": 900,
                                 "common_dividends": 1_800})
    raw = pd.DataFrame(rows)
    cap = pd.DataFrame(cap_rows)
    cap["cet1_ratio"] = cap["cet1_capital"] / cap["rwa"]
    return raw, mapping, cap


@pytest.fixture(scope="session")
def panel(raw_bank_data):
    raw, mapping, _ = raw_bank_data
    return build_panel(raw, mapping)


@pytest.fixture(scope="session")
def capital_df(raw_bank_data):
    return build_capital(raw_bank_data[2])
