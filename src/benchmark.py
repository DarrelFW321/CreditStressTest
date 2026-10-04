"""Reality check against the banks' own IFRS 9 disclosures.

Inputs (hand-collected from each annual report's ECL note):
  data/raw/banks/ifrs9_scenarios.csv    bank, fiscal_year, scenario, variable, horizon, value
      scenario in {base, upside, downside, severe_downside}
      variable in {unemp, gdp_growth, hpi_growth, policy_rate}
  data/raw/banks/ifrs9_sensitivity.csv  bank, fiscal_year, acl_performing_reported,
      acl_performing_downside_100 (allowance if 100% weight on the downside case), gross_loans_total
"""
import pandas as pd
from scipy.stats import spearmanr

from . import config

SCEN_FILE = config.DATA_RAW / "banks" / "ifrs9_scenarios.csv"
SENS_FILE = config.DATA_RAW / "banks" / "ifrs9_sensitivity.csv"


def scenario_severity(ours: pd.DataFrame, fiscal_year: int | None = None) -> pd.DataFrame:
    """Our scenario peaks/troughs next to each bank's disclosed downside assumptions.

    `ours` is scenarios.scenario_summary(...) output.
    """
    disc = pd.read_csv(SCEN_FILE)
    if fiscal_year is None:
        fiscal_year = disc["fiscal_year"].max()
    d = disc[(disc["fiscal_year"] == fiscal_year) & disc["scenario"].isin(["downside", "severe_downside"])]
    table = d.pivot_table(index=["bank", "scenario"], columns="variable", values="value", aggfunc="first")
    ours_view = ours.rename(columns={"unemp_peak": "unemp", "gdp_peak_to_trough_%": "gdp_growth",
                                     "hpi_peak_to_trough_%": "hpi_growth", "policy_rate_end": "policy_rate"})
    ours_view = ours_view[[c for c in table.columns if c in ours_view.columns]]
    ours_view.index = pd.MultiIndex.from_product([["THIS STUDY"], ours_view.index])
    return pd.concat([table, ours_view])


def allowance_sensitivity() -> pd.DataFrame:
    """Each bank's disclosed allowance build if fully weighted to its downside case, bp of loans."""
    s = pd.read_csv(SENS_FILE)
    s = s[s["fiscal_year"] == s["fiscal_year"].max()].copy()
    s["downside_build"] = s["acl_performing_downside_100"] - s["acl_performing_reported"]
    s["downside_build_bps"] = s["downside_build"] / s["gross_loans_total"] * 1e4
    return s.set_index("bank")[["downside_build", "downside_build_bps"]]


def rank_agreement(summary: pd.DataFrame, scenario: str = "adverse") -> dict:
    """Spearman correlation between our cumulative loss rate ranking and the banks' own
    downside allowance sensitivity. Not like-for-like (allowance build vs realized
    losses), so we compare rankings, not levels."""
    ours = summary[summary["scenario"] == scenario].set_index("bank")
    theirs = allowance_sensitivity()
    both = ours.join(theirs, how="inner")
    rho, p = spearmanr(both["cum_loss"], both["downside_build"])
    return {"spearman": rho, "p_value": p, "n": len(both), "table": both[["cum_loss", "downside_build"]]}
