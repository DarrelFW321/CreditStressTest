"""Central assumptions for the stress test.

Every number a reviewer might challenge lives here, with its source or rationale,
so the methodology can be audited (and sensitivity-tested) in one place.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
DATA_TEMPLATES = ROOT / "data" / "templates"
FIGURES = ROOT / "reports" / "figures"

BANKS = ["RY", "TD", "BNS", "BMO", "CM", "NBC"]
BANK_NAMES = {
    "RY": "RBC",
    "TD": "TD",
    "BNS": "Scotiabank",
    "BMO": "BMO",
    "CM": "CIBC",
    "NBC": "National Bank",
}
PORTFOLIOS = ["mortgage", "consumer", "business"]

# Core sample starts with IFRS 9 adoption (fiscal 2018, i.e. Nov 1 2017).
SAMPLE_START = "2017Q4"  # calendar quarter of fiscal Q1 2018
HORIZON = 9  # projection quarters

# --- Macro series -----------------------------------------------------------
BOC_SERIES = {
    "policy_rate": "V39079",  # target for the overnight rate
    "goc_5y": "BD.CDN.5YR.DQ.YLD",  # 5-year GoC benchmark yield
}
STATCAN_VECTORS = {
    "unemp": 2062815,  # LFS unemployment rate, Canada, 15+, SA (14-10-0287-01)
    "gdp": 62305752,  # Real GDP, chained 2017 $, SAAR (36-10-0104-01)
}
FRED_HPI = "QCAN628BIS"  # BIS residential property prices, Canada (nominal)

# --- Regression (satellite model) -------------------------------------------
# Candidate regressors and the sign economic theory requires.
REGRESSORS = {
    "d_unemp": +1,  # q/q change in unemployment (pp), same quarter (IFRS 9 provisions on the outlook)
    "d_unemp_l1": +1,  # q/q change in unemployment (pp), lag 1
    "gdp_yoy": -1,  # real GDP growth y/y (%), contemporaneous
    "hpi_yoy_l1": -1,  # house price growth y/y (%), lag 1
    "hpi_yoy_l2": -1,  # house price growth y/y (%), lag 2
    "rate_l2": +1,  # overnight rate level (%), lag 2
}
# Portfolio-specific candidates (PRD: 3-4 macro variables per portfolio).
# Final specification from the lag search (decisions.md #22).
PORTFOLIO_REGRESSORS = {
    "mortgage": ["d_unemp", "hpi_yoy_l1", "rate_l2"],
    "consumer": ["d_unemp", "gdp_yoy", "rate_l2"],
    "business": ["d_unemp", "gdp_yoy", "rate_l2"],
}
INCLUDE_LAGGED_PCL = True
# Sub-periods for coefficient stability checks.
STABILITY_SPLITS = {
    "pre_covid": ("2017Q4", "2019Q4"),
    "ex_covid_peak": None,  # full sample excluding 2020Q2-2020Q3
    "post_covid": ("2021Q1", None),
}
COVID_PEAK = ["2020Q1", "2020Q2", "2020Q3"]

# --- Scenarios ----------------------------------------------------------------
# Shocks are peak-to-trough versus the jump-off point. Shape parameters set the
# quarter of the trough/peak (1-indexed) within the 9-quarter horizon.
SCENARIOS = {
    "base": {
        # BoC July 2026 MPR: GDP 1.8% in 2027-28, policy rate held at 2.25%,
        # slack (unemployment 6.5-7%) absorbed gradually. Update with the October 2026 MPR.
        "unemp_change": -0.4,
        "gdp_peak_to_trough": 0.0,
        "gdp_trend_growth": 1.8,  # % annualized after trough
        "hpi_change": 0.02,
        "rate_change": 0.0,
        "trough_q": 9,
    },
    "adverse": {
        "unemp_change": 3.0,
        "gdp_peak_to_trough": -3.0,
        "gdp_trend_growth": 1.5,
        "hpi_change": -0.20,
        "rate_change": -1.75,  # cut sharply (floor applied below)
        "trough_q": 5,
    },
    "stagflation": {
        "unemp_change": 4.0,
        "gdp_peak_to_trough": -4.0,
        "gdp_trend_growth": 1.0,
        "hpi_change": -0.30,
        "rate_change": +2.0,  # up 200 bp, sticky
        "trough_q": 6,
    },
}
RATE_FLOOR = 0.25  # effective lower bound used by the BoC in 2020

# --- Vasicek cross-check ------------------------------------------------------
# Basel asset correlations (PRD). Business uses the mid-point of 0.12-0.24.
VASICEK_RHO = {"mortgage": 0.15, "consumer": 0.04, "business": 0.18}
VASICEK_RHO_GRID = {
    "mortgage": [0.10, 0.15, 0.20],
    "consumer": [0.02, 0.04, 0.08],
    "business": [0.12, 0.18, 0.24],
}
# Through-the-cycle 1-year PDs and downturn LGDs. Starting points only:
# calibrate from Pillar 3 IRB tables (PD/LGD by portfolio) in week 5.
BASE_PD = {"mortgage": 0.004, "consumer": 0.020, "business": 0.010}
BASE_PD_GRID = {
    "mortgage": [0.0025, 0.004, 0.006],
    "consumer": [0.015, 0.020, 0.030],
    "business": [0.007, 0.010, 0.015],
}
# Consumer/business LGDs are fixed; the mortgage value is a floor (see below).
LGD = {"mortgage": 0.10, "consumer": 0.75, "business": 0.40}
# Mortgage LGD rises as house prices fall: LGD = max(floor, 1 - (1+dHPI)*(1-cost)/LTV).
# LTV here is that of loans that *default*, well above the uninsured book average
# (~50-55% in SFI disclosures), since defaulters skew to recent, high-LTV originations.
MORTGAGE_DEFAULT_LTV = 0.80
MORTGAGE_SALE_COST = 0.10
# Share of mortgages insured by CMHC/private insurers (credit loss borne by insurer).
# PLACEHOLDER: fill from each bank's SFI "insured vs uninsured" table.
INSURED_SHARE = {b: 0.30 for b in BANKS}
# z mapping: z_t = -(U_t - U_0) / UNEMP_SIGMA, with UNEMP_SIGMA the std. dev. of
# 4-quarter unemployment changes (computed from 1976+ history if available).
UNEMP_SIGMA_DEFAULT = 1.2
# Scales the unemployment -> z mapping (unemployment is a noisy proxy for the
# credit factor). Calibrate in week 5 so 2008-09 conditions reproduce 2009 loss rates.
Z_SCALE = 0.5  # back-test: 2008Q3-2010Q3 path gives ~15 / 470 / 210 bp (decisions.md #23)

# --- Capital ------------------------------------------------------------------
TAX_RATE = 0.265  # Canadian combined statutory rate
# Supervisory severe scenarios typically cut PPNR 25-30% (decisions.md #24).
PPNR_HAIRCUT = {"base": 0.0, "adverse": 0.20, "stagflation": 0.25}
STRESS_OTHER_PCL = True  # scale non-Canadian PCL with the bank's Canadian loss multiple
RWA_GROWTH_PER_Q = {"base": 0.005, "adverse": 0.01, "stagflation": 0.01}  # credit migration
PAY_DIVIDENDS = True  # dividends held at trailing level (CCAR-style conservatism)
# OSFI CET1 requirements for D-SIBs.
CET1_MINIMUM = 0.045
CET1_CONSERVATION = 0.025
CET1_DSIB_SURCHARGE = 0.01
CET1_DSB = 0.035  # Domestic Stability Buffer (check latest OSFI announcement)
CET1_REGULATORY_FLOOR = CET1_MINIMUM + CET1_CONSERVATION + CET1_DSIB_SURCHARGE  # 8.0%
CET1_OSFI_EXPECTATION = CET1_REGULATORY_FLOOR + CET1_DSB  # 11.5%
