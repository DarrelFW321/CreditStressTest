"""Vasicek single-factor cross-check.

PD_stressed = Phi( (Phi^-1(PD_base) - sqrt(rho) * z) / sqrt(1 - rho) )

The systematic factor z is mapped from the scenario's unemployment path:
    z_t = z0 - k * (U_t - U_0) / sigma_U      (k = config.Z_SCALE)
where sigma_U is the std. dev. of 4-quarter unemployment changes and z0 is
chosen so that PD_stressed(z0) = PD_base. (Plugging z = 0 would give the
*median* conditional PD, which sits below the through-the-cycle mean, and
the base scenario would show losses below normal.)
"""
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

from . import config


def stressed_pd(pd_base: float, rho: float, z) -> np.ndarray:
    return norm.cdf((norm.ppf(pd_base) - np.sqrt(rho) * np.asarray(z)) / np.sqrt(1 - rho))


def neutral_z(pd_base: float, rho: float) -> float:
    """z at which the conditional PD equals the unconditional PD."""
    return brentq(lambda z: stressed_pd(pd_base, rho, z) - pd_base, -5, 5)


def mortgage_lgd(hpi_change: np.ndarray) -> np.ndarray:
    """Collateral-driven LGD on uninsured mortgages."""
    recovery = (1 + np.asarray(hpi_change)) * (1 - config.MORTGAGE_SALE_COST) / config.MORTGAGE_DEFAULT_LTV
    return np.maximum(config.LGD["mortgage"], 1 - recovery)


def loss_rate_path(portfolio: str, scen: pd.DataFrame, u0: float, hpi0: float, sigma_u: float,
                   pd_base: float | None = None, rho: float | None = None,
                   insured_share: float = 0.0) -> pd.DataFrame:
    """Quarterly path of z, stressed PD, LGD and annualized loss rate (bp of total portfolio loans)."""
    pd_base = pd_base if pd_base is not None else config.BASE_PD[portfolio]
    rho = rho if rho is not None else config.VASICEK_RHO[portfolio]
    z = neutral_z(pd_base, rho) - config.Z_SCALE * (scen["unemp"].to_numpy() - u0) / sigma_u
    pd_t = stressed_pd(pd_base, rho, z)
    if portfolio == "mortgage":
        lgd = mortgage_lgd(scen["hpi"].to_numpy() / hpi0 - 1)
        exposure_share = 1 - insured_share  # insured losses fall on CMHC / private insurers
    else:
        lgd = np.full(len(scen), config.LGD[portfolio])
        exposure_share = 1.0
    loss_bps = pd_t * lgd * exposure_share * 1e4
    return pd.DataFrame({"z": z, "pd": pd_t, "lgd": lgd, "loss_bps": loss_bps}, index=scen.index)


def cumulative_loss_bps(path: pd.DataFrame) -> float:
    """9-quarter cumulative loss as bp of starting loans (annualized quarterly rates / 4)."""
    return float(path["loss_bps"].sum() / 4)


def project(scenarios: dict[str, pd.DataFrame], loans: pd.DataFrame, u0: float, hpi0: float,
            sigma_u: float) -> pd.DataFrame:
    """Vasicek losses per bank x portfolio x scenario x quarter.

    `loans`: columns bank, portfolio, gross_loans (jump-off balances, static balance sheet).
    """
    rows = []
    for scen_name, scen in scenarios.items():
        for _, r in loans.iterrows():
            ins = config.INSURED_SHARE.get(r.bank, 0.0) if r.portfolio == "mortgage" else 0.0
            path = loss_rate_path(r.portfolio, scen, u0, hpi0, sigma_u, insured_share=ins)
            for q, p in path.iterrows():
                rows.append({"scenario": scen_name, "bank": r.bank, "portfolio": r.portfolio,
                             "quarter": q, "gross_loans": r.gross_loans, "loss_bps": p.loss_bps,
                             "loss": p.loss_bps / 1e4 / 4 * r.gross_loans})
    return pd.DataFrame(rows)


def sensitivity_table(portfolio: str, scen: pd.DataFrame, u0: float, hpi0: float,
                      sigma_u: float) -> pd.DataFrame:
    """Cumulative 9q loss (bp, before insurance) over the rho x base-PD grid."""
    grid = {}
    for rho in config.VASICEK_RHO_GRID[portfolio]:
        grid[f"rho={rho:.2f}"] = {
            f"PD={pd_b:.2%}": cumulative_loss_bps(loss_rate_path(portfolio, scen, u0, hpi0, sigma_u, pd_b, rho))
            for pd_b in config.BASE_PD_GRID[portfolio]
        }
    return pd.DataFrame(grid)


if __name__ == "__main__":
    from .load_macro import load_macro, unemp_sigma
    from .scenarios import build_scenarios, jump_off_levels

    macro = load_macro()
    jo = macro[["unemp", "gdp"]].dropna().index.max()
    scen = build_scenarios(macro, jo)
    start = jump_off_levels(macro, jo)
    sig = unemp_sigma(macro)
    for p in config.PORTFOLIOS:
        print(f"\n{p}: cumulative 9q loss (bp), stagflation")
        print(sensitivity_table(p, scen["stagflation"], start.unemp, start.hpi, sig).round(0))
