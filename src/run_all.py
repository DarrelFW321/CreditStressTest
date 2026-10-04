"""End-to-end pipeline: data -> regression -> scenarios -> projection -> capital -> charts.

    python -m src.run_all              # refresh macro from the APIs
    python -m src.run_all --offline    # use cached macro pulls
    python -m src.run_all --method regression|vasicek|average
"""
import argparse

import pandas as pd

from . import capital, charts, config
from .load_banks import load_and_build
from .load_macro import build_macro_quarterly, load_macro, unemp_sigma
from .regression import fit_all, stability_table
from .scenarios import build_scenarios, jump_off_levels, scenario_summary


def main(offline: bool = False, method: str = "average") -> dict:
    macro = build_macro_quarterly(refresh=not offline) if not offline else load_macro()
    panel, cap = load_and_build()

    models = fit_all(panel, macro)
    for p, m in models.items():
        print(f"\n=== {p}: n={m.nobs}, R2={m.rsquared:.2f}, dropped={m.dropped}")
        print(m.summary_frame().round(3).to_string())
        print(stability_table(panel, macro, m).round(3).to_string())

    jo = capital.jump_off_quarter(panel)
    scen = build_scenarios(macro, jo)
    print(f"\nJump-off {jo}\n", scenario_summary(scen, jump_off_levels(macro, jo)).round(2).to_string())

    out = capital.run(models, scen, panel, cap, macro, unemp_sigma(macro), method)
    out["models"], out["scenarios"] = models, scen

    out_dir = config.DATA_PROCESSED
    out["summary"].to_csv(out_dir / "results_summary.csv", index=False)
    out["losses"].to_csv(out_dir / "results_losses.csv", index=False)
    out["path"].to_csv(out_dir / "results_cet1_path.csv", index=False)
    capital.method_agreement(out).to_csv(out_dir / "results_method_agreement.csv")

    for s in ["adverse", "stagflation"]:
        print(f"\nRanking ({s}, {method}):")
        print(capital.rank(out["summary"], s)[["name", "cet1_start", "cet1_low", "drawdown_bp",
                                                "buffer_vs_osfi_bp", "main_driver"]].round(4).to_string())
    print("\nRanking robustness across methods (stagflation):")
    print(capital.ranking_by_method(out).to_string())

    charts.pcl_history(panel)
    charts.pcl_vs_macro(panel, macro)
    charts.loss_paths(out["losses"], panel)
    for s in ["adverse", "stagflation"]:
        charts.cet1_paths(out["path"], s)
        bridges = {b: capital.waterfall(out["path"], out["capital_inputs"], out["losses"], b, s)
                   for b in out["capital_inputs"].index}
        charts.cet1_waterfall(bridges, s)
        charts.loss_decomposition(out["summary"], s)
    print(f"\nCharts saved to {config.FIGURES}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--method", default="average", choices=["regression", "vasicek", "average"])
    a = ap.parse_args()
    pd.set_option("display.width", 160)
    main(a.offline, a.method)
