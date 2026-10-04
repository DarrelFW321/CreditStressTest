# Implementation Plan: Canadian Bank Credit Stress Test

Companion to [the PRD](PRD%20Canadian%20Bank%20Credit%20Stress%20Test.md). Six weeks at 8–10 h/week, starting **Mon Oct 5, 2026**, finishing **Sun Nov 15, 2026**. Resume-ready checkpoint: **end of week 4 (Nov 1)**.

## Where things stand (Oct 3, end of day: week 1–4 checkpoint reached; see README results)

The code skeleton is built and tested. What is left is mostly **data collection, calibration, and writing**.

| Component | File | Status |
|---|---|---|
| Macro pulls (BoC Valet, StatCan, BIS house prices via FRED) | `src/load_macro.py` | ✅ Working on live data. Unemployment from 1976, GDP from 1961 |
| Bank panel builder (fiscal→calendar mapping, PCL ratios, validation) | `src/load_banks.py` | ✅ Built. **Needs the hand-collected CSVs** |
| Satellite regression (bank FE, lagged PCL, sign selection, stability) | `src/regression.py` | ✅ Recovers known coefficients on synthetic data |
| Scenarios (base / adverse / stagflation, 9q) | `src/scenarios.py` | ✅ Working on live data. Base case is a placeholder |
| Vasicek cross-check (z mapping, HPI-linked mortgage LGD, sensitivity grid) | `src/vasicek.py` | ✅ Built. **Needs calibration (week 5)** |
| Capital (CET1 path, waterfall, ranking, method robustness) | `src/capital.py` | ✅ Built. Bridge reconciles exactly (tested) |
| IFRS 9 benchmark | `src/benchmark.py` | ✅ Built. Needs disclosure CSVs |
| Charts | `src/charts.py` | ✅ All PRD charts + CET1 paths + loss decomposition |
| Pipeline / notebook / tests | `src/run_all.py`, `notebooks/analysis.ipynb`, `tests/` | ✅ 7 tests pass |

Every assumption is in [`src/config.py`](src/config.py). Change it there, never inline.

---

## Week 1 (Oct 5–11): Bank data, the heaviest week (~10–12 h)

Goal: `data/raw/banks/pcl_loans.csv` and `capital.csv` filled for all 6 banks, FQ1 2018 → FQ3 2026 (35 quarters).

- [x] Download SFI packages: `make packages` (done Oct 3: 54 files, Q4 of FY2018–2025 + FQ3 2026 for all six banks, in `data/raw/banks/packages/<BANK>/`, git-ignored). Excel for most; PDF for TD 2018–22, Scotiabank 2018–20, BMO 2018–19 and 2021–22. Each Q4 package shows 5–8 trailing quarters. Use `--all-quarters` if a gap appears.
- [x] **RBC extracted automatically** (`make extract`): 35 quarters × 6 products + capital, FQ1 2018–FQ3 2026. Stage 1–2 PCL is allocated (decisions.md #17); spot-check 3 quarters against the PDF.
- [x] **CIBC extracted automatically** (`make extract`): 35 quarters × 4 products + capital. Loans grossed up from net, Stage 1–2 PCL allocated, CET1 capital = ratio × RWA (decisions.md #19–21).
- [x] **TD, Scotiabank, BMO, National Bank extracted automatically** (Excel + `pdftotext` for PDF-only years); judgment calls in decisions.md #25–36.
- [x] For each bank-quarter, record **Canadian** PCL and gross loans by the bank's own labels. See [docs/data_collection.md](docs/data_collection.md) for where to find each table.
- [x] Record Stage 1–2 vs Stage 3 PCL wherever disclosed (often only at total-bank or segment level; leave blank otherwise).
- [x] Capital: CET1 capital, RWA, CET1 ratio, pre-provision pre-tax earnings, **total-bank PCL**, common dividends.
- [x] Update `data/portfolio_map.csv`. Every row starts as `VERIFY`; replace that with what you actually saw. Log HELOC decisions in [docs/decisions.md](docs/decisions.md).
- [x] `make banks` runs with no unmapped-label errors. Investigate every warning (loan jumps >15% q/q usually mean an acquisition (RBC–HSBC Canada in FQ2 2024; National Bank–Canadian Western Bank in FQ2 2025) or a relabel).

**Done when:** panel has 6 banks × 3 portfolios × ~35 quarters, CET1/RWA reconciles to the reported ratio within 5 bp.

## Week 2 (Oct 12–18): Macro data and exploration (~8 h)

- [x] `make macro` (already working). Decide whether to replace the BIS series with CREA MLS HPI (monthly, better) by saving `data/raw/house_prices/hpi.csv`.
- [x] Set the **base scenario** from the latest BoC Monetary Policy Report (October 2026 MPR) and big-bank economics forecasts. Edit `SCENARIOS["base"]` in config.
- [ ] Notebook section 1: PCL history by bank (`pcl_history`), PCL vs unemployment / house prices (`pcl_vs_macro`), per-portfolio history.
- [ ] Write down 3 observations for the report (e.g., the size of the 2020 Stage 1–2 build and 2021 release, which bank's business book is noisiest).
- [ ] Collect 2008–09 PCL ratios by bank from annual reports (qualitative benchmark only; pre-IFRS 9).

**Done when:** you can explain the 2020 spike and the 2021 releases bank by bank.

## Week 3 (Oct 19–25): Regression (~8–10 h)

- [x] `make regression`. For each portfolio, review signs, magnitudes, R², dropped variables.
- [x] Stability table: full sample vs pre-COVID vs ex-COVID-peak vs post-COVID. Coefficients should keep sign; flag anything that flips.
- [ ] Try the performing/impaired split (`target="pcl_perf_bps"` / `"pcl_imp_bps"`) where data allows; performing should react faster.
- [x] Sensitivity: lag choices (unemployment lag 0/1/2, HPI lag 1/2/4), with/without lagged PCL. Keep the specification simple (3–4 variables).
- [ ] Sanity check: long-run multiplier (β/(1–ρ)) on unemployment × 2009 shock (+2.6 pp) should give a loss increase in the order of magnitude seen in 2009.
- [x] Record the final specification in `config.PORTFOLIO_REGRESSORS` and in docs/decisions.md (#22).

**Known issue to manage:** COVID is the only stress in sample and government support muted losses → coefficients likely *understate* recession sensitivity. Don't fight this in the regression; that's what the Vasicek cross-check is for.

## Week 4 (Oct 26–Nov 1): Scenarios and projection (~10 h), **resume-ready checkpoint**

- [x] Review scenario paths (`python -m src.scenarios`) against history: adverse peak unemployment ~9.7% (vs 8.7% in 2009), stagflation ~10.7% with rates +200 bp.
- [x] `make all` with `--method regression` first. Inspect loss paths, CET1 paths, waterfall.
- [x] Sanity check the capital mechanics: PPNR haircut, dividends held, RWA migration, tax rate, other-PCL run rate.
- [x] Draft the ranking and the main driver per bank.
- [x] **Put the 3 resume bullets in with real numbers** (PRD template). Commit and push the repo with a first README results section.

**Done when:** resume bullets have real numbers and the repo is public.

## Week 5 (Nov 2–8): Vasicek and benchmarking (~10 h)

- [ ] Calibrate Vasicek inputs from Pillar 3 IRB disclosures (CR6 tables: PD and LGD by portfolio): `BASE_PD`, `LGD`, `INSURED_SHARE` (from SFI insured/uninsured mortgage tables), `MORTGAGE_DEFAULT_LTV`.
- [x] **Back-test the z mapping:** set the scenario to 2008–09 conditions (+2.6 pp unemployment) and tune `Z_SCALE` so Vasicek loss rates land near 2009 actual PCL ratios. This is the key calibration. Without it, stagflation (+4 pp ≈ z of –3) produces near-Basel-99.9% losses.
- [ ] Run sensitivity tables (ρ × base PD) for each portfolio; include in report.
- [ ] `method_agreement`: Vasicek/regression ratio per portfolio. PRD success = "within a reasonable range". Define it up front (e.g., 0.5×–2×) and explain gaps.
- [ ] Collect IFRS 9 disclosures from the FY2025 annual reports (FY2026 ones publish early December, after the project ends): downside scenario assumptions and the "100% pessimistic" allowance sensitivity → `ifrs9_scenarios.csv`, `ifrs9_sensitivity.csv`.
- [ ] Benchmark: scenario severity table and Spearman rank agreement.
- [ ] Final ranking under `average` method; check `ranking_by_method` and the mapping sensitivity (e.g., HELOCs in mortgage vs consumer). Does the most/least exposed bank change?

## Week 6 (Nov 9–15): Polish (~8–10 h)

- [ ] README: headline result in the first 3 lines, ranking table, 3 charts (PCL history, loss paths, CET1 waterfall), how to run.
- [ ] Stress test report (6–8 pp) → `reports/stress_test_report.pdf`. Outline below.
- [ ] Sector view (1–2 pp) → `reports/sector_view.pdf`.
- [ ] Prepare answers to the PRD's 5 interview questions (write them down).
- [ ] LinkedIn post with the waterfall chart.
- [ ] Feedback from an upper-year or club member; one revision pass.

---

## Report outline (6–8 pages)

1. **Summary** (½ p): ranking, CET1 drawdowns, main driver, one-line method.
2. **Scenarios** (1 p): table vs 2008–09 and vs banks' disclosed downside cases; why stagflation matters for mortgages (renewal shock).
3. **Data and portfolio mapping** (½ p): sources, IFRS 9 sample, mapping table, judgment calls.
4. **Method 1: satellite regression** (1 p): specification, coefficient table, stability.
5. **Method 2: Vasicek** (1 p): z mapping, calibration back-test, sensitivity table.
6. **Results** (1.5 p): loss paths, cumulative losses by bank × portfolio, CET1 waterfall, ranking + robustness.
7. **Benchmark** (½ p): our results vs IFRS 9 disclosures.
8. **Limitations** (½ p): one downturn in sample, government support, management overlays, static balance sheet, Canadian-only credit, no funding/market risk, PPNR held simple.

## Sector view outline (1–2 pages)

Ranking and why → which bank's credit (senior / NVCC spreads) looks rich or cheap given its resilience → equity angle (dividend safety, buyback capacity) → what would change the call. Link to the Canadian Credit Relative Value project.

## Success criteria checklist (from PRD)

- [ ] Regression signs correct and stable across sub-periods
- [ ] Vasicek within the predefined range of the regression for each portfolio
- [ ] 9q losses + CET1 impact for all 6 banks × 3 scenarios
- [ ] Compared against banks' IFRS 9 downside disclosures
- [ ] Ranked view with reasons
- [ ] Done by Nov 15

## Risks to watch this plan specifically

| Risk | Early sign | Response |
|---|---|---|
| Week 1 overruns | RBC alone takes >4 h | Collect annual (Q4) SFIs first for trailing quarters; fill gaps later |
| Product × geography PCL not disclosed for some bank | Only segment-level PCL | Allocate segment PCL by loan share; flag in decisions.md and test ranking without that bank |
| Regression signs wrong for business portfolio | Lumpy single-name losses | Use fewer regressors; lean on Vasicek for business; say so |
| Vasicek far from regression | Ratio > 3× | Expected for severe scenarios (regression trained on supported COVID). Report both and explain; don't force agreement |
