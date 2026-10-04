"""Satellite model: PCL ratio on lagged macro variables, per portfolio.

PCL_{b,t} = alpha_b + beta' X_t + rho * PCL_{b,t-1} + e_{b,t}

Pooled across the six banks with bank fixed effects. Standard errors are
clustered by quarter: the macro regressors are common to all banks, so
residuals are correlated across banks within a quarter. (With T ~ 35 the
Nickell bias on rho from fixed effects + lagged DV is small, ~ -(1+rho)/T;
note it in the report rather than switching to GMM.)
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm

from . import config


@dataclass
class SatelliteModel:
    portfolio: str
    target: str
    regressors: list[str]
    params: pd.Series
    bse: pd.Series
    pvalues: pd.Series
    nobs: int
    rsquared: float
    dropped: list[str] = field(default_factory=list)

    @property
    def bank_effects(self) -> pd.Series:
        fe = self.params[self.params.index.str.startswith("fe_")]
        return fe.rename(lambda s: s[3:])

    @property
    def rho(self) -> float:
        return float(self.params.get("pcl_lag", 0.0))

    def long_run(self) -> pd.Series:
        """Long-run effect of a permanent 1-unit change in each regressor."""
        return self.params[self.regressors] / (1 - self.rho)

    def predict_one(self, bank: str, x: dict, pcl_lag: float) -> float:
        y = self.bank_effects[bank] + sum(self.params[r] * x[r] for r in self.regressors)
        if "pcl_lag" in self.params:
            y += self.rho * pcl_lag
        return float(y)

    def summary_frame(self) -> pd.DataFrame:
        keys = self.regressors + (["pcl_lag"] if "pcl_lag" in self.params else [])
        out = pd.DataFrame({"coef": self.params[keys], "se": self.bse[keys], "p": self.pvalues[keys]})
        out["expected_sign"] = [config.REGRESSORS.get(k, +1) for k in keys]
        out["sign_ok"] = np.sign(out["coef"]) == out["expected_sign"]
        return out


def model_frame(panel: pd.DataFrame, macro: pd.DataFrame, portfolio: str,
                target: str = "pcl_bps") -> pd.DataFrame:
    df = panel[panel["portfolio"] == portfolio].sort_values(["bank", "quarter"]).copy()
    df["pcl_lag"] = df.groupby("bank")[target].shift(1)
    feats = macro[list(config.REGRESSORS)]
    df = df.merge(feats, left_on="quarter", right_index=True, how="left")
    return df


def fit(panel: pd.DataFrame, macro: pd.DataFrame, portfolio: str, regressors: list[str],
        target: str = "pcl_bps", sample: tuple | None = None,
        drop_quarters: list[str] | None = None) -> SatelliteModel:
    df = model_frame(panel, macro, portfolio, target)
    if sample:
        start, end = sample
        if start:
            df = df[df["quarter"] >= pd.Period(start, "Q")]
        if end:
            df = df[df["quarter"] <= pd.Period(end, "Q")]
    if drop_quarters:
        df = df[~df["quarter"].isin(pd.PeriodIndex(drop_quarters, freq="Q"))]

    cols = list(regressors) + (["pcl_lag"] if config.INCLUDE_LAGGED_PCL else [])
    df = df.dropna(subset=[target] + cols)
    fe = pd.get_dummies(df["bank"], prefix="fe", prefix_sep="_", dtype=float)
    X = pd.concat([fe, df[cols]], axis=1)
    res = sm.OLS(df[target], X).fit(cov_type="cluster",
                                   cov_kwds={"groups": df["quarter"].astype(str).factorize()[0]})
    return SatelliteModel(portfolio, target, list(regressors), res.params, res.bse,
                          res.pvalues, int(res.nobs), float(res.rsquared))


def select_by_sign(panel, macro, portfolio, target="pcl_bps", candidates=None) -> SatelliteModel:
    """Drop wrong-signed regressors one at a time (worst t-stat first) and refit."""
    regs = list(candidates or config.PORTFOLIO_REGRESSORS[portfolio])
    dropped = []
    while regs:
        m = fit(panel, macro, portfolio, regs, target)
        t = m.params[regs] / m.bse[regs]
        wrong = {r: t[r] * config.REGRESSORS[r] for r in regs if np.sign(m.params[r]) != config.REGRESSORS[r]}
        if not wrong:
            m.dropped = dropped
            return m
        worst = min(wrong, key=wrong.get)
        regs.remove(worst)
        dropped.append(worst)
    raise ValueError(f"No correctly signed regressors for {portfolio}/{target}")


def stability_table(panel, macro, model: SatelliteModel) -> pd.DataFrame:
    """Re-estimate the chosen specification on sub-periods; coefficients side by side."""
    rows = {"full": model.params}
    for name, window in config.STABILITY_SPLITS.items():
        try:
            if window is None:
                m = fit(panel, macro, model.portfolio, model.regressors, model.target,
                        drop_quarters=config.COVID_PEAK)
            else:
                m = fit(panel, macro, model.portfolio, model.regressors, model.target, sample=window)
            rows[name] = m.params
        except (ValueError, np.linalg.LinAlgError):
            continue
    keys = model.regressors + (["pcl_lag"] if "pcl_lag" in model.params else [])
    return pd.DataFrame(rows).loc[keys]


def fit_all(panel, macro, target="pcl_bps") -> dict[str, SatelliteModel]:
    return {p: select_by_sign(panel, macro, p, target) for p in config.PORTFOLIOS}


if __name__ == "__main__":
    from .load_banks import read_processed
    from .load_macro import load_macro

    panel, macro = read_processed("bank_panel"), load_macro()
    for p, m in fit_all(panel, macro).items():
        print(f"\n=== {p}  (n={m.nobs}, R2={m.rsquared:.2f}, dropped={m.dropped})")
        print(m.summary_frame().round(3))
        print(stability_table(panel, macro, m).round(3))
