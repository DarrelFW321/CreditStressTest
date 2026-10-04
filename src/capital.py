"""9-quarter loss projection and CET1 impact.

Static balance sheet: loan balances held at jump-off levels. Each quarter,
    pre-tax income = PPNR * (1 - haircut) - Canadian credit losses - other PCL
    CET1_t = CET1_{t-1} + pre-tax * (1 - tax) - dividends
    RWA_t  = RWA_{t-1} * (1 + migration)
"Other PCL" (U.S. / international, out of scope) starts at its trailing 4-quarter run
rate and is stressed in proportion to the bank's Canadian losses (scenario / base).
"""
import pandas as pd

from . import config
from . import vasicek
from .regression import SatelliteModel


def jump_off_quarter(panel: pd.DataFrame) -> pd.Period:
    """Latest quarter reported by every bank."""
    return panel.groupby("bank")["quarter"].max().min()


def jump_off_loans(panel: pd.DataFrame, jump_off: pd.Period) -> pd.DataFrame:
    jo = panel[panel["quarter"] == jump_off]
    return jo[["bank", "portfolio", "gross_loans", "pcl_bps"]].reset_index(drop=True)


def capital_inputs(capital: pd.DataFrame, panel: pd.DataFrame, jump_off: pd.Period) -> pd.DataFrame:
    """Jump-off CET1/RWA plus trailing-4-quarter quarterly averages of PPNR, dividends and other PCL."""
    window = capital[(capital["quarter"] > jump_off - 4) & (capital["quarter"] <= jump_off)]
    canada_pcl = (panel[(panel["quarter"] > jump_off - 4) & (panel["quarter"] <= jump_off)]
                  .groupby(["bank", "quarter"])["pcl_total"].sum().rename("pcl_canada").reset_index())
    window = window.merge(canada_pcl, on=["bank", "quarter"], how="left")
    window["pcl_other"] = (window["pcl_total_bank"] - window["pcl_canada"]).clip(lower=0)
    trailing = window.groupby("bank")[["ppt_earnings", "common_dividends", "pcl_other"]].mean()
    if trailing["pcl_other"].isna().any():
        print("WARNING: pcl_total_bank missing for", list(trailing.index[trailing["pcl_other"].isna()]),
              "- other PCL set to 0 (overstates income)")
        trailing["pcl_other"] = trailing["pcl_other"].fillna(0.0)
    start = capital[capital["quarter"] == jump_off].set_index("bank")[["cet1_capital", "rwa"]]
    out = start.join(trailing)
    out["cet1_ratio"] = out["cet1_capital"] / out["rwa"]
    return out


def project_regression(models: dict[str, SatelliteModel], scenarios: dict[str, pd.DataFrame],
                       loans: pd.DataFrame) -> pd.DataFrame:
    """Dynamic projection: each quarter's predicted PCL ratio feeds the next quarter's lag."""
    rows = []
    for scen_name, scen in scenarios.items():
        for _, r in loans.iterrows():
            m = models[r.portfolio]
            lag = r.pcl_bps
            for q, x in scen.iterrows():
                bps = m.predict_one(r.bank, x.to_dict(), lag)
                lag = bps
                rows.append({"scenario": scen_name, "bank": r.bank, "portfolio": r.portfolio,
                             "quarter": q, "gross_loans": r.gross_loans, "loss_bps": bps,
                             "loss": bps / 1e4 / 4 * r.gross_loans})
    return pd.DataFrame(rows)


def combine(reg: pd.DataFrame, vas: pd.DataFrame, method: str = "average") -> pd.DataFrame:
    if method == "regression":
        return reg.copy()
    if method == "vasicek":
        return vas.copy()
    keys = ["scenario", "bank", "portfolio", "quarter"]
    m = reg.merge(vas, on=keys, suffixes=("_reg", "_vas"))
    m["loss_bps"] = (m["loss_bps_reg"] + m["loss_bps_vas"]) / 2
    m["loss"] = (m["loss_reg"] + m["loss_vas"]) / 2
    m["gross_loans"] = m["gross_loans_reg"]
    return m[keys + ["gross_loans", "loss_bps", "loss"]]


def other_pcl_multiplier(loss: float, base_loss: float) -> float:
    """Stress non-Canadian PCL like the bank's Canadian book (decisions.md #13): scenario / base losses."""
    if not config.STRESS_OTHER_PCL or base_loss <= 0:
        return 1.0
    return max(loss / base_loss, 1.0)


def capital_path(losses: pd.DataFrame, cap: pd.DataFrame, scenario: str) -> pd.DataFrame:
    haircut = config.PPNR_HAIRCUT[scenario]
    growth = config.RWA_GROWTH_PER_Q[scenario]
    sub = losses[losses["scenario"] == scenario]
    by_q = sub.groupby(["bank", "quarter"])["loss"].sum()
    base = losses[losses["scenario"] == "base"].groupby(["bank", "quarter"])["loss"].sum()
    rows = []
    for bank, c in cap.iterrows():
        cet1, rwa = c.cet1_capital, c.rwa
        for q in sorted(sub["quarter"].unique()):
            loss = by_q.get((bank, q), 0.0)
            ppnr = c.ppt_earnings * (1 - haircut)
            other = c.pcl_other * other_pcl_multiplier(loss, base.get((bank, q), loss))
            pretax = ppnr - loss - other
            net = pretax * (1 - config.TAX_RATE)
            divs = c.common_dividends if config.PAY_DIVIDENDS else 0.0
            cet1 += net - divs
            rwa *= 1 + growth
            rows.append({"scenario": scenario, "bank": bank, "quarter": q, "ppnr": ppnr,
                         "credit_loss": loss, "other_pcl": other, "net_income": net,
                         "dividends": divs, "cet1_capital": cet1, "rwa": rwa, "cet1_ratio": cet1 / rwa})
    return pd.DataFrame(rows)


def summarize(path: pd.DataFrame, cap: pd.DataFrame, losses: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (scen, bank), g in path.groupby(["scenario", "bank"]):
        low = g.loc[g["cet1_ratio"].idxmin()]
        start = cap.loc[bank, "cet1_ratio"]
        cum = losses[(losses["scenario"] == scen) & (losses["bank"] == bank)].groupby("portfolio")["loss"].sum()
        rows.append({
            "scenario": scen, "bank": bank,
            "cet1_start": start, "cet1_low": low.cet1_ratio, "low_quarter": low.quarter,
            "drawdown_bp": (start - low.cet1_ratio) * 1e4,
            "buffer_vs_osfi_bp": (low.cet1_ratio - config.CET1_OSFI_EXPECTATION) * 1e4,
            "buffer_vs_floor_bp": (low.cet1_ratio - config.CET1_REGULATORY_FLOOR) * 1e4,
            "cum_loss": cum.sum(),
            **{f"loss_{p}": cum.get(p, 0.0) for p in config.PORTFOLIOS},
            "loss_non_canadian": g["other_pcl"].sum(),
        })
    return pd.DataFrame(rows)


def waterfall(path: pd.DataFrame, cap: pd.DataFrame, losses: pd.DataFrame, bank: str,
              scenario: str) -> pd.Series:
    """CET1 ratio bridge (bp) from jump-off to the stressed low point.

    Flows are expressed against starting RWA; the residual is the RWA growth effect.
    """
    g = path[(path["scenario"] == scenario) & (path["bank"] == bank)].reset_index(drop=True)
    i_low = g["cet1_ratio"].idxmin()
    upto = g.iloc[: i_low + 1]
    q_low = upto["quarter"].iloc[-1]
    rwa0 = cap.loc[bank, "rwa"]
    after_tax = 1 - config.TAX_RATE
    l = losses[(losses["scenario"] == scenario) & (losses["bank"] == bank) & (losses["quarter"] <= q_low)]
    by_p = l.groupby("portfolio")["loss"].sum()
    bridge = {"start": cap.loc[bank, "cet1_ratio"] * 1e4,
              "ppnr_after_tax": upto["ppnr"].sum() * after_tax / rwa0 * 1e4}
    for p in config.PORTFOLIOS:
        bridge[f"loss_{p}"] = -by_p.get(p, 0.0) * after_tax / rwa0 * 1e4
    bridge["other_pcl"] = -upto["other_pcl"].sum() * after_tax / rwa0 * 1e4
    bridge["dividends"] = -upto["dividends"].sum() / rwa0 * 1e4
    low = g.loc[i_low, "cet1_ratio"] * 1e4
    bridge["rwa_growth"] = low - sum(bridge.values())
    bridge["low"] = low
    return pd.Series(bridge)


def run(models, scenarios, panel, capital, macro, sigma_u, method="average") -> dict:
    from .scenarios import jump_off_levels

    jo = jump_off_quarter(panel)
    loans = jump_off_loans(panel, jo)
    cap = capital_inputs(capital, panel, jo)
    start = jump_off_levels(macro, jo)
    reg = project_regression(models, scenarios, loans)
    vas = vasicek.project(scenarios, loans, start["unemp"], start["hpi"], sigma_u)
    out = {"jump_off": jo, "regression": reg, "vasicek": vas, "capital_inputs": cap}
    for m in ["regression", "vasicek", "average"]:
        losses = combine(reg, vas, m)
        path = pd.concat([capital_path(losses, cap, s) for s in scenarios])
        out[f"path_{m}"] = path
        out[f"summary_{m}"] = summarize(path, cap, losses)
        out[f"losses_{m}"] = losses
    out["path"], out["summary"], out["losses"] = (out[f"path_{method}"], out[f"summary_{method}"],
                                                  out[f"losses_{method}"])
    return out


def rank(summary: pd.DataFrame, scenario: str = "stagflation") -> pd.DataFrame:
    s = summary[summary["scenario"] == scenario].sort_values("drawdown_bp", ascending=False)
    s = s.assign(rank=range(1, len(s) + 1), name=s["bank"].map(config.BANK_NAMES))
    parts = s[[f"loss_{p}" for p in config.PORTFOLIOS] + ["loss_non_canadian"]]
    s["main_driver"] = parts.idxmax(axis=1).str.replace("loss_", "").str.replace("_", "-")
    return s.set_index("rank")


def method_agreement(out: dict) -> pd.DataFrame:
    """Cumulative 9q loss rate (bp of loans) by method; the PRD's cross-check criterion."""
    frames = []
    for m in ["regression", "vasicek"]:
        cum = out[m].groupby(["scenario", "bank", "portfolio"])["loss_bps"].sum() / 4
        frames.append(cum.rename(m))
    df = pd.concat(frames, axis=1)
    df["ratio_vas_to_reg"] = df["vasicek"] / df["regression"]
    return df


def ranking_by_method(out: dict, scenario: str = "stagflation") -> pd.DataFrame:
    """Does the ranking survive a change of method? (Robustness table for the report.)"""
    cols = {}
    for m in ["regression", "vasicek", "average"]:
        r = rank(out[f"summary_{m}"], scenario)
        cols[m] = r["bank"].tolist()
    return pd.DataFrame(cols, index=range(1, len(cols["average"]) + 1))
