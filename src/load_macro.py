"""Pull Canadian macro data (BoC Valet, Statistics Canada, BIS/CREA house prices).

Outputs data/processed/macro_quarterly.csv: calendar-quarter levels plus the
regression features. Raw pulls are cached in data/raw/macro so the pipeline
still runs offline.
"""
import json

import numpy as np
import pandas as pd
import requests

from . import config

BOC_URL = "https://www.bankofcanada.ca/valet/observations/{series}/json"
STATCAN_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
MACRO_RAW = config.DATA_RAW / "macro"


def _cache(name: str, df: pd.DataFrame) -> pd.DataFrame:
    MACRO_RAW.mkdir(parents=True, exist_ok=True)
    df.to_csv(MACRO_RAW / f"{name}.csv")
    return df


def _read_cache(name: str) -> pd.DataFrame:
    return pd.read_csv(MACRO_RAW / f"{name}.csv", index_col=0, parse_dates=True)


def fetch_boc(start: str = "2000-01-01") -> pd.DataFrame:
    """Daily overnight target and 5y GoC yield."""
    series = ",".join(config.BOC_SERIES.values())
    resp = requests.get(BOC_URL.format(series=series), params={"start_date": start}, timeout=60)
    resp.raise_for_status()
    rows = []
    for obs in resp.json()["observations"]:
        row = {"date": obs["d"]}
        for name, code in config.BOC_SERIES.items():
            row[name] = float(obs[code]["v"]) if code in obs and obs[code].get("v") else np.nan
        rows.append(row)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return _cache("boc_daily", df.set_index("date"))


def fetch_statcan(n_periods: int = 700) -> dict[str, pd.Series]:
    """Unemployment (monthly, from 1976) and real GDP (quarterly, from 1961)."""
    payload = [{"vectorId": v, "latestN": n_periods} for v in config.STATCAN_VECTORS.values()]
    resp = requests.post(STATCAN_URL, data=json.dumps(payload),
                         headers={"Content-Type": "application/json"}, timeout=60)
    resp.raise_for_status()
    by_vector = {item["object"]["vectorId"]: item["object"]["vectorDataPoint"] for item in resp.json()}
    out = {}
    for name, vec in config.STATCAN_VECTORS.items():
        pts = by_vector[vec]
        s = pd.Series({pd.Timestamp(p["refPer"]): p["value"] for p in pts}, name=name).sort_index()
        out[name] = _cache(f"statcan_{name}", s.to_frame())[name]
    return out


def fetch_hpi() -> pd.Series:
    """House price index. Uses a manually saved CREA/Teranet file if present.

    Drop a CSV with columns `date,hpi` at data/raw/house_prices/hpi.csv (monthly
    CREA MLS HPI composite benchmark, or Teranet-National Bank composite) to
    override the BIS quarterly series pulled from FRED.
    """
    manual = config.DATA_RAW / "house_prices" / "hpi.csv"
    if manual.exists():
        df = pd.read_csv(manual, parse_dates=["date"]).set_index("date")
        return df["hpi"].sort_index()
    df = pd.read_csv(FRED_URL.format(series=config.FRED_HPI))
    df.columns = ["date", "hpi"]
    df["date"] = pd.to_datetime(df["date"])
    df["hpi"] = pd.to_numeric(df["hpi"], errors="coerce")
    return _cache("hpi_bis", df.set_index("date"))["hpi"]


def to_quarterly(s: pd.Series, how: str = "mean") -> pd.Series:
    s = s.dropna()
    q = s.groupby(s.index.to_period("Q"))
    return q.mean() if how == "mean" else q.last()


def add_features(levels: pd.DataFrame) -> pd.DataFrame:
    """Derive regression features from quarterly levels.

    Shared by history and scenario projection so the transformations are identical.
    Expects columns unemp (%), gdp (level), hpi (index), policy_rate (%).
    """
    df = levels.sort_index().copy()
    df["d_unemp"] = df["unemp"].diff()
    df["gdp_yoy"] = df["gdp"].pct_change(4, fill_method=None) * 100
    df["hpi_yoy"] = df["hpi"].pct_change(4, fill_method=None) * 100
    df["d_unemp_l1"] = df["d_unemp"].shift(1)
    df["hpi_yoy_l1"] = df["hpi_yoy"].shift(1)
    df["hpi_yoy_l2"] = df["hpi_yoy"].shift(2)
    df["rate_l2"] = df["policy_rate"].shift(2)
    return df


def build_macro_quarterly(refresh: bool = True) -> pd.DataFrame:
    if refresh:
        boc = fetch_boc()
        sc = fetch_statcan()
        hpi = fetch_hpi()
    else:
        boc = _read_cache("boc_daily")
        sc = {k: _read_cache(f"statcan_{k}")[k] for k in config.STATCAN_VECTORS}
        manual = config.DATA_RAW / "house_prices" / "hpi.csv"
        hpi = fetch_hpi() if manual.exists() else _read_cache("hpi_bis")["hpi"]

    levels = pd.DataFrame({
        "unemp": to_quarterly(sc["unemp"]),
        "gdp": to_quarterly(sc["gdp"], "last"),
        "hpi": to_quarterly(hpi),
        "policy_rate": to_quarterly(boc["policy_rate"]),
        "goc_5y": to_quarterly(boc["goc_5y"]),
    })
    macro = add_features(levels)
    macro.index.name = "quarter"
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    macro.to_csv(config.DATA_PROCESSED / "macro_quarterly.csv")
    return macro


def load_macro() -> pd.DataFrame:
    df = pd.read_csv(config.DATA_PROCESSED / "macro_quarterly.csv")
    df["quarter"] = pd.PeriodIndex(df["quarter"], freq="Q")
    return df.set_index("quarter")


def unemp_sigma(macro: pd.DataFrame) -> float:
    """Std. dev. of 4-quarter unemployment changes (long history), for the Vasicek z mapping."""
    s = macro["unemp"].diff(4).dropna()
    return float(s.std()) if len(s) > 40 else config.UNEMP_SIGMA_DEFAULT


if __name__ == "__main__":
    m = build_macro_quarterly()
    print(m.loc["2017Q4":].round(2).to_string())
