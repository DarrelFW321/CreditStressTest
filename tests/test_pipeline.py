import numpy as np
import pandas as pd
import pytest

from src import capital, config, vasicek
from src.load_banks import fiscal_to_calendar, validate_panel
from src.regression import fit, select_by_sign, stability_table
from src.scenarios import build_scenarios, jump_off_levels, scenario_summary

from .conftest import TRUE_BETA, TRUE_RHO


def test_fiscal_quarter_mapping():
    assert fiscal_to_calendar(2018, 1) == pd.Period("2017Q4")
    assert fiscal_to_calendar(2018, 2) == pd.Period("2018Q1")
    assert fiscal_to_calendar(2018, 4) == pd.Period("2018Q3")
    assert fiscal_to_calendar(2026, 3) == pd.Period("2026Q2")


def test_panel_aggregates_labels_to_portfolios(panel):
    assert set(panel["portfolio"]) == set(config.PORTFOLIOS)
    assert panel.groupby(["bank", "quarter"])["portfolio"].nunique().eq(3).all()
    assert validate_panel(panel) == [] or all("PCL ratio" in w for w in validate_panel(panel))


def test_regression_recovers_known_coefficients(panel, macro):
    m = fit(panel, macro, "consumer", list(TRUE_BETA))
    for k, b in TRUE_BETA.items():
        assert np.sign(m.params[k]) == np.sign(b)
        assert m.params[k] == pytest.approx(b, rel=0.3, abs=1.0)
    assert m.rho == pytest.approx(TRUE_RHO, abs=0.1)


def test_sign_selection_and_stability(panel, macro):
    m = select_by_sign(panel, macro, "business")
    assert m.summary_frame()["sign_ok"].all()
    assert "full" in stability_table(panel, macro, m).columns


def test_scenarios_hit_specified_shocks(macro):
    scen = build_scenarios(macro, "2026Q2")
    summ = scenario_summary(scen, jump_off_levels(macro, "2026Q2"))
    assert summ.loc["adverse", "unemp_change_pp"] == pytest.approx(3.0, abs=0.01)
    assert summ.loc["stagflation", "hpi_peak_to_trough_%"] == pytest.approx(-30, abs=0.1)
    assert summ.loc["adverse", "gdp_peak_to_trough_%"] == pytest.approx(-3, abs=0.1)
    assert all(len(v) == config.HORIZON for v in scen.values())
    assert scen["adverse"][list(config.REGRESSORS)].notna().all().all()


def test_vasicek_properties():
    z0 = vasicek.neutral_z(0.02, 0.04)
    assert vasicek.stressed_pd(0.02, 0.04, z0) == pytest.approx(0.02)
    assert vasicek.stressed_pd(0.02, 0.04, -2) > vasicek.stressed_pd(0.02, 0.04, 0)
    assert vasicek.mortgage_lgd(-0.30) > vasicek.mortgage_lgd(0.0)


def test_capital_end_to_end(panel, capital_df, macro):
    models = {p: select_by_sign(panel, macro, p) for p in config.PORTFOLIOS}
    jo = capital.jump_off_quarter(panel)
    scen = build_scenarios(macro, jo)
    out = capital.run(models, scen, panel, capital_df, macro, sigma_u=1.3)
    s = out["summary"].set_index(["scenario", "bank"])
    # Severe scenario must hurt more than base for every bank
    for b in config.BANKS:
        assert s.loc[("stagflation", b), "cum_loss"] > s.loc[("base", b), "cum_loss"]
    # Waterfall bridge must reconcile start -> low exactly
    br = capital.waterfall(out["path"], out["capital_inputs"], out["losses"], "TD", "stagflation")
    assert br.drop(["low"]).sum() == pytest.approx(br["low"])
    r = capital.rank(out["summary"], "stagflation")
    assert list(r.index) == list(range(1, 7))
    assert capital.ranking_by_method(out).shape == (6, 3)
