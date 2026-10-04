"""Build the bank x portfolio x quarter panel from hand-collected SFI figures.

Inputs (C$ millions, one row per bank / fiscal quarter / reported line item):
  data/raw/banks/pcl_loans.csv   PCL and gross loans by the bank's own labels
  data/raw/banks/capital.csv     CET1 capital, RWA, pre-provision earnings, dividends
  data/portfolio_map.csv         bank label -> mortgage / consumer / business / exclude

Outputs:
  data/processed/bank_panel.csv    PCL ratios (bp) by bank, portfolio, calendar quarter
  data/processed/bank_capital.csv  capital inputs by bank, calendar quarter
"""
import pandas as pd

from . import config

PCL_FILE = config.DATA_RAW / "banks" / "pcl_loans.csv"
CAPITAL_FILE = config.DATA_RAW / "banks" / "capital.csv"
MAP_FILE = config.ROOT / "data" / "portfolio_map.csv"


def fiscal_to_calendar(fiscal_year: int, fiscal_quarter: int) -> pd.Period:
    """Big 6 fiscal years end Oct 31, so fiscal Q1 (Nov-Jan) shares two months
    with calendar Q4 of the prior year. Map each fiscal quarter to the calendar
    quarter it overlaps most: FQ1 FY2018 -> 2017Q4, FQ2 -> 2018Q1, etc."""
    return pd.Period(f"{fiscal_year - 1}Q4", freq="Q") + (fiscal_quarter - 1)


def _add_quarter(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["quarter"] = [fiscal_to_calendar(y, q) for y, q in zip(df["fiscal_year"], df["fiscal_quarter"])]
    return df


def map_portfolios(raw: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    merged = raw.merge(mapping[["bank", "segment_label", "portfolio"]],
                       on=["bank", "segment_label"], how="left")
    unmapped = merged[merged["portfolio"].isna()][["bank", "segment_label"]].drop_duplicates()
    if len(unmapped):
        raise ValueError(f"Unmapped segment labels; add them to {MAP_FILE.name}:\n{unmapped}")
    bad = set(merged["portfolio"]) - set(config.PORTFOLIOS) - {"exclude"}
    if bad:
        raise ValueError(f"Unknown portfolio names in mapping: {bad}")
    return merged[merged["portfolio"] != "exclude"]


def build_panel(raw: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    df = _add_quarter(map_portfolios(raw, mapping))
    value_cols = ["pcl_total", "pcl_performing", "pcl_impaired", "gross_loans"]
    for c in value_cols:
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    # min_count=1 keeps "not disclosed" as NaN rather than 0
    panel = (df.groupby(["bank", "portfolio", "quarter"])[value_cols]
               .sum(min_count=1).reset_index()
               .sort_values(["bank", "portfolio", "quarter"]))

    g = panel.groupby(["bank", "portfolio"])["gross_loans"]
    panel["avg_loans"] = (panel["gross_loans"] + g.shift(1)) / 2
    panel["avg_loans"] = panel["avg_loans"].fillna(panel["gross_loans"])
    for src, dst in [("pcl_total", "pcl_bps"), ("pcl_performing", "pcl_perf_bps"),
                     ("pcl_impaired", "pcl_imp_bps")]:
        panel[dst] = panel[src] * 4 / panel["avg_loans"] * 1e4
    panel["loan_growth_qoq"] = g.pct_change(fill_method=None)
    return panel.reset_index(drop=True)


def validate_panel(panel: pd.DataFrame) -> list[str]:
    """Return human-readable warnings; nothing here is fatal."""
    warnings = []
    counts = panel.groupby(["bank", "quarter"])["portfolio"].nunique()
    for (bank, q), n in counts[counts < len(config.PORTFOLIOS)].items():
        warnings.append(f"{bank} {q}: only {n} of {len(config.PORTFOLIOS)} portfolios")
    jumps = panel[panel["loan_growth_qoq"].abs() > 0.15]
    for _, r in jumps.iterrows():
        warnings.append(f"{r.bank} {r.portfolio} {r.quarter}: loans moved "
                        f"{r.loan_growth_qoq:+.0%} q/q (acquisition or relabel? check mapping)")
    neg = panel[panel["pcl_bps"] < -50]
    for _, r in neg.iterrows():
        warnings.append(f"{r.bank} {r.portfolio} {r.quarter}: PCL ratio {r.pcl_bps:.0f} bp (large release)")
    return warnings


def build_capital(raw: pd.DataFrame) -> pd.DataFrame:
    df = _add_quarter(raw)
    df["cet1_ratio_calc"] = df["cet1_capital"] / df["rwa"]
    if "cet1_ratio" in df:
        gap = (df["cet1_ratio_calc"] - df["cet1_ratio"]).abs()
        off = df[gap > 0.0005]
        if len(off):
            print(f"WARNING: {len(off)} rows where CET1/RWA differs from reported ratio by >5 bp")
    return df.sort_values(["bank", "quarter"]).reset_index(drop=True)


def load_and_build() -> tuple[pd.DataFrame, pd.DataFrame]:
    mapping = pd.read_csv(MAP_FILE)
    raw = pd.read_csv(PCL_FILE)
    if raw.empty:
        raise SystemExit(f"{PCL_FILE.relative_to(config.ROOT)} has no rows yet. "
                         "Fill it from the banks' SFI packages (see docs/data_collection.md).")
    panel = build_panel(raw, mapping)
    capital = build_capital(pd.read_csv(CAPITAL_FILE))
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    panel.to_csv(config.DATA_PROCESSED / "bank_panel.csv", index=False)
    capital.to_csv(config.DATA_PROCESSED / "bank_capital.csv", index=False)
    for w in validate_panel(panel):
        print("WARNING:", w)
    return panel, capital


def read_processed(name: str) -> pd.DataFrame:
    df = pd.read_csv(config.DATA_PROCESSED / f"{name}.csv")
    df["quarter"] = pd.PeriodIndex(df["quarter"], freq="Q")
    return df


if __name__ == "__main__":
    p, c = load_and_build()
    print(p.groupby(["bank", "portfolio"])["pcl_bps"].describe().round(1))
