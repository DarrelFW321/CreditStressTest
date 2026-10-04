# Bank data collection guide

All figures in **C$ millions**, one row per bank × fiscal quarter × line item. Fiscal years end **Oct 31** for all six banks (FQ1 = Nov–Jan). Use bank codes `RY, TD, BNS, BMO, CM, NBC` (not `NA`: pandas reads that as a missing value).

## Getting the packages

`make packages` downloads the Q4 SFI for fiscal 2018–2025 plus FQ3 2026 for all six banks into `data/raw/banks/packages/<BANK>/<BANK>_FY<year>Q<q>_SFI.xlsx|pdf` (Excel where the bank publishes it). Each Q4 package shows 5–8 trailing quarters (RBC: 8), so together they cover FQ1 2018 onward. Use the newest package that shows a quarter, since it includes restatements. `python -m src.fetch_packages --all-quarters` gets every quarter if needed.

## Where to look

Every bank publishes a quarterly **Supplementary Financial Information** package (Excel + PDF) on its investor relations site, next to the quarterly results. You need three kinds of tables:

| Need | Typical SFI table name | Notes |
|---|---|---|
| PCL by product, **Canada only** | "Provision for credit losses by geography / industry" | Use the Canada column. If only total-bank is given by product, allocate by Canadian loan share and log it |
| Gross loans by product, Canada | "Loans and acceptances by geography" / "Gross loans by product" | Period-end balances |
| Stage split | "Allowance for credit losses" / "PCL on performing vs impaired" | Often total or segment level only; fill when available at product × Canada level |
| Capital | "Regulatory capital and ratios" (SFI or Supplementary Regulatory Capital Disclosure) | CET1 capital, RWA, CET1 ratio |
| Earnings | Income statement summary | **Pre-provision pre-tax earnings** = income before taxes + total PCL. Also total-bank PCL and common dividends |
| Insured mortgages | "Residential mortgages: insured vs uninsured" (SFI or MD&A) | For `config.INSURED_SHARE` |
| PD / LGD by portfolio | Pillar 3 report, table **CR6** | For Vasicek calibration (week 5) |
| IFRS 9 scenarios | Annual report, ECL note / "Credit risk" MD&A section | Scenario assumptions table + "allowance if 100% pessimistic" sensitivity |

The SFI product labels differ by bank. The starting mapping is in [`data/portfolio_map.csv`](../data/portfolio_map.csv); every row is marked `VERIFY`. Replace each note with what you actually found.

## Files to fill

### `data/raw/banks/pcl_loans.csv`
| column | meaning |
|---|---|
| bank, fiscal_year, fiscal_quarter | e.g. `RY, 2024, 2` |
| segment_label | the bank's label, exactly as in `portfolio_map.csv` |
| pcl_total | PCL for the quarter (not YTD!) |
| pcl_performing, pcl_impaired | Stage 1+2 and Stage 3 PCL if disclosed, else blank |
| gross_loans | period-end gross loans |
| source, notes | file name + sheet/page, e.g. `RY_SFI_Q2_2024.xlsx p.18` |

### `data/raw/banks/capital.csv`
`cet1_capital, rwa, cet1_ratio` (decimal, e.g. 0.131), `ppt_earnings` (quarterly pre-provision pre-tax), `pcl_total_bank` (all geographies), `common_dividends`, `source, notes`.

### `data/raw/banks/ifrs9_scenarios.csv`
Long format: `bank, fiscal_year, scenario (base|upside|downside|severe_downside), variable (unemp|gdp_growth|hpi_growth|policy_rate), horizon (e.g. "next 12m" or "peak"), value`. Record the Canadian figures.

### `data/raw/banks/ifrs9_sensitivity.csv`
`acl_performing_reported`, `acl_performing_downside_100` (allowance on performing loans if 100% weighted to the pessimistic scenario), `gross_loans_total`.

## Pitfalls

- **YTD vs quarterly.** Some tables are year-to-date; difference them.
- **Restatements.** Prefer the most recent package that shows a quarter (later packages may restate segments).
- **Acquisitions.** RBC–HSBC Canada (FQ2 2024) and National Bank–Canadian Western Bank (FQ2 2025) create loan jumps; HSBC/CWB also brought initial Stage 1–2 allowances through PCL. Note the quarter and consider a dummy.
- **Acceptances.** Bankers' acceptances were phased out with CDOR in 2024; exclude acceptances throughout for consistency.
- **Sign.** PCL releases are negative; keep the sign.
- **Units.** Some packages are in thousands or billions; convert to millions.
