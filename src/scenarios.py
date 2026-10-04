"""Base, adverse-recession and severe-stagflation macro paths (9 quarters).

Scenarios are specified as peak-to-trough shocks in config.SCENARIOS and turned
into smooth quarterly level paths from the jump-off quarter. Features are then
derived with the same transformation used on history (load_macro.add_features),
so lags and y/y growth rates splice correctly onto actual data.
"""
import numpy as np
import pandas as pd

from . import config
from .load_macro import add_features

LEVELS = ["unemp", "gdp", "hpi", "policy_rate"]


def _ramp(q: np.ndarray, trough: int) -> np.ndarray:
    """Smooth 0 -> 1 path reaching 1 at quarter `trough`, flat afterwards."""
    x = np.clip(q / trough, 0, 1)
    return (1 - np.cos(np.pi * x)) / 2


def jump_off_levels(macro: pd.DataFrame, jump_off: pd.Period) -> pd.Series:
    """Latest known level of each variable at or before the jump-off quarter.

    Macro releases lag (house prices by about a quarter), so missing values are
    carried forward. Record this in the report's assumptions.
    """
    hist = macro.loc[:jump_off, LEVELS].ffill()
    return hist.iloc[-1]


def build_path(spec: dict, start: pd.Series, horizon: int = config.HORIZON,
               unemp_recovery: float = 0.25) -> pd.DataFrame:
    q = np.arange(1, horizon + 1)
    T = spec["trough_q"]
    ramp = _ramp(q, T)

    # Unemployment: rises to peak at T, then retraces a share of the shock by the horizon end.
    after = np.clip((q - T) / max(horizon - T, 1), 0, 1)
    unemp = start["unemp"] + spec["unemp_change"] * (ramp - unemp_recovery * after * (spec["unemp_change"] > 0))

    # Real GDP: falls peak-to-trough to T, then grows at trend.
    trend_q = (1 + spec["gdp_trend_growth"] / 100) ** 0.25
    gdp = start["gdp"] * (1 + spec["gdp_peak_to_trough"] / 100 * ramp)
    if spec["gdp_peak_to_trough"] == 0:
        gdp = start["gdp"] * trend_q ** q
    else:
        gdp = np.where(q > T, gdp[T - 1] * trend_q ** (q - T), gdp)

    # House prices: decline to trough one quarter after the macro trough, then flat.
    hpi = start["hpi"] * (1 + spec["hpi_change"] * _ramp(q, min(T + 1, horizon)))

    # Policy rate: moves over the first three quarters, then sticky.
    rate = np.maximum(start["policy_rate"] + spec["rate_change"] * _ramp(q, 3), config.RATE_FLOOR)

    return pd.DataFrame({"unemp": unemp, "gdp": gdp, "hpi": hpi, "policy_rate": rate})


def build_scenarios(macro: pd.DataFrame, jump_off: str | pd.Period,
                    specs: dict | None = None) -> dict[str, pd.DataFrame]:
    """Return {scenario: DataFrame indexed by projection quarter with levels + features}."""
    jump_off = pd.Period(jump_off, freq="Q")
    start = jump_off_levels(macro, jump_off)
    hist = macro.loc[:jump_off, LEVELS].ffill().iloc[-8:]
    out = {}
    for name, spec in (specs or config.SCENARIOS).items():
        path = build_path(spec, start)
        path.index = pd.period_range(jump_off + 1, periods=len(path), freq="Q")
        full = add_features(pd.concat([hist, path]))
        out[name] = full.loc[path.index]
    return out


def scenario_summary(scen: dict[str, pd.DataFrame], start: pd.Series) -> pd.DataFrame:
    """Peak / trough statistics for the report's scenario table."""
    rows = {}
    for name, df in scen.items():
        rows[name] = {
            "unemp_peak": df["unemp"].max(),
            "unemp_change_pp": df["unemp"].max() - start["unemp"],
            "gdp_peak_to_trough_%": (df["gdp"].min() / start["gdp"] - 1) * 100,
            "hpi_peak_to_trough_%": (df["hpi"].min() / start["hpi"] - 1) * 100,
            "policy_rate_end": df["policy_rate"].iloc[-1],
        }
    return pd.DataFrame(rows).T


if __name__ == "__main__":
    from .load_macro import load_macro

    macro = load_macro()
    jo = macro[["unemp", "gdp"]].dropna().index.max()
    scen = build_scenarios(macro, jo)
    print(f"Jump-off {jo}\n", scenario_summary(scen, jump_off_levels(macro, jo)).round(2))
    for k, v in scen.items():
        print(f"\n{k}\n", v[LEVELS + list(config.REGRESSORS)].round(2))
