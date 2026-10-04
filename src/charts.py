"""Report and README charts (static PNGs, light background).

Colors follow a validated categorical order: each bank keeps its slot across
every chart, so identity never depends on rank or on which banks are shown.
"""
import matplotlib.pyplot as plt
import pandas as pd

from . import config

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
BANK_COLOR = dict(zip(config.BANKS, SERIES))
SCENARIO_COLOR = {"base": "#2a78d6", "adverse": "#eb6834", "stagflation": "#1baf7a"}
UP, DOWN, TOTAL = "#2a78d6", "#e34948", "#8a8984"
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e6e5e1"

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "axes.titlecolor": INK,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "xtick.color": INK_2, "ytick.color": INK_2, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "lines.linewidth": 2, "legend.frameon": False, "font.size": 10, "axes.axisbelow": True,
})


def _save(fig, name):
    config.FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(config.FIGURES / f"{name}.png", dpi=160, bbox_inches="tight")
    return fig


def pcl_history(panel: pd.DataFrame, portfolio: str | None = None, name="pcl_history"):
    """PCL ratio by bank (all Canadian portfolios, or one), with the 2020 spike shaded."""
    df = panel if portfolio is None else panel[panel["portfolio"] == portfolio]
    agg = df.groupby(["bank", "quarter"])[["pcl_total", "avg_loans"]].sum()
    bps = (agg["pcl_total"] * 4 / agg["avg_loans"] * 1e4).unstack("bank")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = bps.index.to_timestamp()
    ax.axvspan(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-09-30"), color=GRID, alpha=0.6, lw=0)
    for bank in config.BANKS:
        if bank in bps:
            ax.plot(x, bps[bank], color=BANK_COLOR[bank], label=config.BANK_NAMES[bank])
    ax.axhline(0, color=INK_2, lw=0.8)
    ax.set_ylabel("PCL ratio (bp of avg. loans, annualized)")
    ax.set_title(f"PCL ratio by bank - {portfolio or 'all Canadian lending'}")
    ax.legend(ncol=3, loc="upper right")
    return _save(fig, name if portfolio is None else f"{name}_{portfolio}")


def pcl_vs_macro(panel: pd.DataFrame, macro: pd.DataFrame, var="unemp", name="pcl_vs_unemp"):
    """System-wide PCL ratio beside a macro driver: two panels, never two y-axes."""
    agg = panel.groupby("quarter")[["pcl_total", "avg_loans"]].sum()
    bps = agg["pcl_total"] * 4 / agg["avg_loans"] * 1e4
    m = macro.loc[bps.index.min():bps.index.max(), var]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True)
    a1.plot(bps.index.to_timestamp(), bps, color=SERIES[0])
    a1.set_title("Big 6 Canadian PCL ratio (bp)")
    a2.plot(m.index.to_timestamp(), m, color=SERIES[1])
    a2.set_title({"unemp": "Unemployment rate (%)", "hpi_yoy": "House prices, y/y (%)"}.get(var, var))
    return _save(fig, name)


def loss_paths(losses: pd.DataFrame, history: pd.DataFrame | None = None, name="loss_paths"):
    """System-wide quarterly loss rate under each scenario, optionally spliced onto history."""
    fig, ax = plt.subplots(figsize=(9, 4.5))
    if history is not None:
        agg = history.groupby("quarter")[["pcl_total", "avg_loans"]].sum()
        h = agg["pcl_total"] * 4 / agg["avg_loans"] * 1e4
        ax.plot(h.index.to_timestamp(), h, color=INK_2, label="Actual")
    for scen, color in SCENARIO_COLOR.items():
        s = losses[losses["scenario"] == scen]
        if s.empty:
            continue
        g = s.groupby("quarter")[["loss", "gross_loans"]].sum()
        ratio = g["loss"] * 4 / g["gross_loans"] * 1e4
        ax.plot(ratio.index.to_timestamp(), ratio, color=color, label=scen.capitalize())
    ax.set_ylabel("Loss rate (bp, annualized)")
    ax.set_title("Projected credit losses, Big 6 Canadian lending")
    ax.legend(loc="upper left")
    return _save(fig, name)


def cet1_paths(path: pd.DataFrame, scenario: str, name="cet1_paths"):
    g = path[path["scenario"] == scenario].pivot(index="quarter", columns="bank", values="cet1_ratio") * 100
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for bank in config.BANKS:
        if bank in g:
            ax.plot(g.index.to_timestamp(), g[bank], color=BANK_COLOR[bank], label=config.BANK_NAMES[bank])
    ax.axhline(config.CET1_OSFI_EXPECTATION * 100, color=DOWN, lw=1, ls="--")
    ax.text(g.index.to_timestamp()[0], config.CET1_OSFI_EXPECTATION * 100 + 0.05,
            "OSFI D-SIB expectation incl. DSB", color=INK_2, fontsize=8)
    ax.set_ylabel("CET1 ratio (%)")
    ax.set_title(f"CET1 ratio path - {scenario}")
    ax.legend(ncol=3, loc="lower left")
    return _save(fig, f"{name}_{scenario}")


def cet1_waterfall(bridges: dict[str, pd.Series], scenario: str, name="cet1_waterfall"):
    """One small-multiple waterfall per bank: start -> flows -> stressed low (bp of RWA)."""
    banks = [b for b in config.BANKS if b in bridges]
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), sharey=True)
    for ax, bank in zip(axes.flat, banks):
        br = bridges[bank] / 100  # bp -> %
        labels = list(br.index)
        levels = br.drop(["start", "low"]).cumsum() + br["start"]
        lo = min(levels.min(), br["low"], config.CET1_OSFI_EXPECTATION * 100) - 1
        hi = max(levels.max(), br["start"]) + 0.6
        level = 0.0
        for i, (k, v) in enumerate(br.items()):
            if k in ("start", "low"):
                ax.bar(i, v - lo, bottom=lo, color=TOTAL, width=0.7)
                level = v
                ax.text(i, v + 0.1, f"{v:.1f}", ha="center", va="bottom", fontsize=8, color=INK)
            else:
                ax.bar(i, v, bottom=level, color=UP if v >= 0 else DOWN, width=0.7)
                level += v
        ax.set_ylim(lo, hi)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels([l.replace("loss_", "").replace("_", " ") for l in labels],
                           rotation=60, ha="right", fontsize=8)
        ax.set_title(config.BANK_NAMES[bank], fontsize=10)
        ax.axhline(config.CET1_OSFI_EXPECTATION * 100, color=DOWN, lw=1, ls="--")
    for ax in axes.flat[len(banks):]:
        ax.set_visible(False)
    axes[0, 0].set_ylabel("CET1 ratio (%)")
    fig.suptitle(f"CET1 bridge to stressed low point - {scenario}", x=0.01, ha="left",
                 fontweight="bold", color=INK)
    fig.tight_layout()
    return _save(fig, f"{name}_{scenario}")


def loss_decomposition(summary: pd.DataFrame, scenario: str, name="loss_decomposition"):
    """Cumulative 9q losses by portfolio, as % of starting CET1 capital, one bar per bank."""
    s = summary[summary["scenario"] == scenario].set_index("bank").reindex(config.BANKS).dropna(how="all")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    bottom = pd.Series(0.0, index=s.index)
    colors = dict(zip(config.PORTFOLIOS, SERIES[:3]))
    for p in config.PORTFOLIOS:
        v = s[f"loss_{p}"] / 1e3  # C$ bn
        ax.bar([config.BANK_NAMES[b] for b in s.index], v, bottom=bottom, color=colors[p],
               label=p.capitalize(), width=0.6, edgecolor="#fcfcfb", linewidth=2)
        bottom += v
    ax.set_ylabel("Cumulative 9-quarter losses (C$ bn)")
    ax.set_title(f"What drives each bank's losses - {scenario}")
    ax.legend(loc="upper right")
    return _save(fig, f"{name}_{scenario}")
