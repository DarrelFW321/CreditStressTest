# PRD: Canadian Bank Credit Stress Test

Oct 3, 2026 · @Darrel Wihandi

## Overview

Build a model that projects credit losses for Canada's Big 6 banks under macro stress scenarios, then rank which bank is most exposed and what that means for its capital.

**Problem.** Bank investors, regulators, and risk teams all ask the same question: how bad do loan losses get in a recession, and which bank is hit hardest? The answer depends on each bank's loan mix, especially its exposure to mortgages, consumer credit, and business lending.

**Why it matters for recruiting.** This project fits bank risk teams (stress testing, credit risk, model validation) and also gives a sector view useful in capital markets and equity research interviews. It extends the Vasicek and expected credit loss (ECL) work from the PwC internship from a single client to the whole Canadian banking system.

## Goals and success criteria

The project succeeds if it produces a defensible ranking of bank vulnerability under stress, backed by two independent methods that roughly agree.

| Goal | Success criterion |
| --- | --- |
| Working loss model | Macro regression of provision ratios with sensible signs (higher unemployment → higher losses) and stable coefficients across sub-periods |
| Cross-check | Vasicek-based projection lands within a reasonable range of the regression result for each loan portfolio |
| Scenario output | 9-quarter projected losses and CET1 capital impact for each of the Big 6 under three scenarios |
| Reality check | Results compared against the banks' own disclosed IFRS 9 downside scenarios |
| Clear conclusion | A ranked view of which bank is most and least exposed, with the reason |
| Delivered on time | Finished within 6 weeks at about 8–10 hours per week |

## Scope

The model covers the Big 6 banks' Canadian lending, split into three portfolios, using quarterly data from fiscal 2018 onward.

**Banks:** RBC, TD, Scotiabank, BMO, CIBC, National Bank.

**Portfolios**

| Portfolio | Main macro drivers | Why it matters |
| --- | --- | --- |
| Residential mortgages and HELOCs | House prices, unemployment, interest rates | Largest exposure; low losses but high concentration |
| Consumer (cards, auto, personal loans) | Unemployment, interest rates | Highest loss rates; reacts fastest in a downturn |
| Business and government | GDP growth, interest rates | Lumpy losses; differs most across banks |

**Time period:** fiscal 2018 onward is the core sample, because banks switched to IFRS 9 accounting that year and provisions before then are not comparable. Earlier data is used only as a qualitative check.

**In scope:** data collection, macro regression, Vasicek cross-check, three scenarios, 9-quarter projection, CET1 impact, bank ranking.

**Out of scope:** U.S. and international portfolios, market risk and trading losses, funding and liquidity stress, regulatory-grade model validation.

## Data requirements

Everything comes from free public sources; no Bloomberg needed.

| Data | Source | Fields | Frequency |
| --- | --- | --- | --- |
| Provisions and loan balances | Each bank's quarterly Supplementary Financial Information package (investor relations site) | PCL by portfolio, gross loans, Stage 1/2/3 allowances | Quarterly |
| Capital | Same packages, or each bank's Pillar 3 report | CET1 capital, risk-weighted assets, pre-provision pre-tax earnings | Quarterly |
| Banks' own scenarios | Annual reports (IFRS 9 / ECL note) | Base and downside assumptions for unemployment, GDP, house prices; allowance sensitivity | Annual |
| Unemployment, GDP | Statistics Canada | National unemployment rate, real GDP growth | Monthly / quarterly |
| Policy rate, bond yields | Bank of Canada Valet API | Overnight rate, 5-year GoC yield | Daily, resample to quarterly |
| House prices | CREA MLS Home Price Index or Teranet–National Bank HPI | National benchmark price | Monthly |

**Cleaning steps**

1. Align fiscal quarters (banks' year ends October 31) to calendar quarters for macro data.
2. Compute the PCL ratio: annualized PCL divided by average gross loans, in basis points.
3. Map each bank's portfolio labels to the three common portfolios; document any judgment calls.
4. Separate provisions on performing loans (Stage 1 and 2) from impaired loans (Stage 3) where disclosed, since they respond to the economy differently.

## Methodology

Two independent methods project losses, then capital impact and a ranking follow from their combined result.

**Step 1: Macro regression ("satellite model").** For each portfolio, regress the PCL ratio on macro variables across all six banks, with bank fixed effects to capture differences in risk appetite:

```latex
\text{PCL}_{b,t} = \alpha_b + \beta_1 \Delta\text{Unemp}_{t-1} + \beta_2 \text{GDP}_{t} + \beta_3 \Delta\text{HPI}_{t-2} + \beta_4 \text{Rate}_{t-2} + \rho\,\text{PCL}_{b,t-1} + \varepsilon_{b,t}
```

Lags reflect that losses trail the economy. Keep variables only where the sign makes economic sense.

**Step 2: Vasicek cross-check.** Translate each scenario into a stressed default rate with the single-factor Vasicek model, the same framework behind Basel capital rules:

```latex
\text{PD}_{\text{stressed}} = \Phi\left( \frac{\Phi^{-1}(\text{PD}_{\text{base}}) - \sqrt{\rho}\, z}{\sqrt{1-\rho}} \right)
```

Here z is the economy's state (negative in a downturn), mapped from the scenario's unemployment path. Use Basel asset correlations as ρ: 0.15 for mortgages, 0.04 for credit cards, and 0.12–0.24 for business loans. Expected loss = stressed PD × loss given default × exposure.

**Step 3: Scenario design.** Three 9-quarter paths, calibrated to Canadian history (unemployment peaked near 8.7% in 2009) and to the banks' own disclosed downside cases:

| Scenario | Unemployment | Real GDP | House prices | Policy rate |
| --- | --- | --- | --- | --- |
| Base | Consensus forecast | Consensus forecast | Flat to modest growth | Consensus path |
| Adverse recession | +3 pp from today | −3% peak to trough | −20% | Cut sharply |
| Severe stagflation | +4 pp from today | −4% peak to trough | −30% | Up 200 bp, sticky inflation |

The stagflation case matters because higher rates hit mortgage renewals at the same time unemployment rises.

**Step 4: Capital impact.** Project cumulative 9-quarter losses, offset them with pre-provision earnings after tax, and express the result as a change in each bank's CET1 ratio. Compare the low point against OSFI's regulatory minimums.

**Step 5: Rank and explain.** Rank banks by CET1 drawdown, then decompose each bank's losses by portfolio to show what drives the ranking.

## Deliverables

Four outputs, each usable on its own in applications and interviews.

| Deliverable | Contents | Used for |
| --- | --- | --- |
| GitHub repo | Clean code, README with headline results and charts, saved dataset | Resume link, technical interviews |
| Stress test report (6–8 pages) | Scenarios, both methods, results by bank and portfolio, comparison with banks' disclosures, limitations | Risk interviews, deeper conversations |
| Sector view (1–2 pages) | Which bank is most and least resilient and why, plus what it implies for bank credit and equity | Capital markets and equity research interviews |
| Resume bullets | 2–3 bullets with method, number, and finding | Projects section |

**Charts to include:** PCL ratio history by bank with the 2020 spike; projected loss paths under each scenario; CET1 ratio waterfall from starting level to stressed low point for each bank.

## Tech stack and repo structure

Python end to end; Excel only for collecting figures from the banks' packages.

- **Python:** pandas, numpy, statsmodels (panel regression), scipy (normal distribution for Vasicek), matplotlib
- **Data collection:** banks' supplementary packages come as Excel files; pull the needed rows into one tidy CSV
- **Macro data:** Bank of Canada Valet API and Statistics Canada downloads, scripted so they refresh

```text
canadian-bank-stress-test/
├── README.md              # headline results, key charts, bank ranking
├── data/
│   ├── raw/               # bank packages, StatCan, BoC, house price files
│   └── processed/         # quarterly bank × portfolio panel
├── src/
│   ├── load_macro.py      # BoC and StatCan pulls
│   ├── load_banks.py      # PCL, loans, capital by bank and portfolio
│   ├── regression.py      # satellite model per portfolio
│   ├── vasicek.py         # stressed PDs and expected loss
│   ├── scenarios.py       # base, adverse, stagflation paths
│   └── capital.py         # 9-quarter projection, CET1 impact
├── notebooks/
│   └── analysis.ipynb     # walkthrough with charts
└── reports/
    ├── stress_test_report.pdf
    └── sector_view.pdf
```

## Timeline

Six weeks at about 8–10 hours per week; a resume-ready version exists after week 4.

- [ ] **Week 1 — Bank data:** download supplementary packages for all six banks, build the quarterly PCL, loans, and capital panel
- [ ] **Week 2 — Macro data and exploration:** pull StatCan, BoC, and house price data; chart PCL ratios against unemployment and house prices
- [ ] **Week 3 — Regression:** fit the satellite model per portfolio, check signs and stability
- [ ] **Week 4 — Scenarios and projection:** build three scenarios, project 9-quarter losses and CET1 impact; add bullets to resume
- [ ] **Week 5 — Vasicek and benchmarking:** run the cross-check, compare with banks' disclosed downside cases, finalize ranking
- [ ] **Week 6 — Polish:** README, charts, report, sector view, LinkedIn post; get feedback from an upper-year or club member

Week 1 is the heaviest because portfolio labels differ across banks. Budget extra time there rather than rushing the mapping.

## Risks and mitigations

The biggest risk is a short history with only one real stress event; the Vasicek cross-check exists mainly to address it.

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Only one downturn since 2018 (COVID), distorted by government support | Regression underestimates true recession losses | Use Vasicek as a second method; benchmark against banks' own downside scenarios and 2008–09 loss levels |
| IFRS 9 provisions are forward-looking | Provisions jump before losses appear, muddying lags | Model performing (Stage 1–2) and impaired (Stage 3) provisions separately where disclosed |
| Portfolio labels differ across banks | Comparisons become apples to oranges | Document the mapping in a table; test ranking sensitivity to it |
| Small sample (6 banks × \~34 quarters) | Overfitting, unstable coefficients | Pool banks with fixed effects; keep 3–4 macro variables per portfolio |
| Vasicek inputs are assumptions | Results swing with ρ and base PD | Show a sensitivity table rather than one number |
| School workload | Project stalls | Week 4 version is already resume-ready |

## Resume and interview positioning

This project pairs with Canadian Credit Relative Value: one shows how banks lose money on loans, the other how markets price that risk. Numbers below are placeholders; fill them with real results.

**Draft resume bullets**

- Built a macro stress test of Big 6 Canadian bank credit losses in Python, regressing provision ratios on unemployment, GDP, house prices, and rates across \[3\] loan portfolios
- Projected 9-quarter losses under adverse and stagflation scenarios, estimating CET1 drawdowns of \[80–190\] bp and identifying \[bank\] as most exposed due to \[portfolio\] concentration
- Cross-validated results with a Vasicek single-factor model and benchmarked against banks' disclosed IFRS 9 downside scenarios

**Interview questions to prepare**

- Why did you choose those scenarios, and how severe are they compared with 2008–09?
- Why does the stagflation case hurt mortgages more than a normal recession?
- What does your model miss? (Hint: government support, management overlays, funding stress.)
- If you were a bank equity or credit investor, what would you do with this result?
- How does this connect to your ECL work at PwC?

The PwC link is the strongest talking point: there you applied Vasicek to one client's receivables; here you scaled the same idea to the whole banking system.
