# Methodology decisions log

One row per judgment call. Update it as you go; this table becomes the report's assumptions appendix and answers "why did you do X?" in interviews.

| # | Decision | Choice | Rationale | Alternative / sensitivity |
|---|---|---|---|---|
| 1 | Fiscal → calendar quarter | Fiscal quarter mapped to the calendar quarter sharing 2 of its 3 months (FQ1 → prior-year Q4) | All Big 6 year-ends are Oct 31; one-month offset is small vs quarterly macro data | Aggregate monthly macro to exact fiscal quarters |
| 2 | PCL ratio | Annualized quarterly PCL / average of opening and closing gross loans, bp | PRD definition; average loans neutralize growth | Period-end loans |
| 3 | Sample | FQ1 2018 onward | IFRS 9 adoption; pre-2018 provisions are incurred-loss and not comparable | 2008–09 used only as a qualitative benchmark |
| 4 | HELOCs | Mortgage portfolio where separately disclosed (TD), otherwise left in consumer | PRD groups HELOCs with mortgages; not every bank splits them | Ranking sensitivity with HELOCs moved (week 5) |
| 5 | Regression standard errors | Clustered by quarter | Macro regressors are common across banks → within-quarter residual correlation | Driscoll–Kraay |
| 6 | Variable selection | Drop wrong-signed variables one at a time, worst t-stat first | PRD: keep variables only where the sign makes economic sense | Fixed specification with sign restrictions |
| 7 | Lagged dependent variable with bank FE | Kept; Nickell bias ≈ –(1+ρ)/T ≈ –0.04 with T≈35 | Small relative to estimation noise | Arellano–Bond (overkill for 6 banks) |
| 8 | House price index | BIS residential property prices (FRED: QCAN628BIS) by default | Free, scripted, quarterly | CREA MLS HPI or Teranet via `data/raw/house_prices/hpi.csv` |
| 9 | Jump-off macro values | Last available value carried forward where releases lag | House prices lag ~1 quarter | — |
| 10 | Vasicek z mapping | z = z0 − k·ΔU/σ(ΔU₄q), z0 sets PD(z0) = PD_base | z=0 would give the median, not mean, PD, so base-case losses would sit below normal | Calibrate k (`Z_SCALE`) to 2009 losses |
| 11 | Mortgage LGD | max(10%, 1 − (1+ΔHPI)(1−10% cost)/80% LTV of defaulters) on uninsured share only | Captures collateral channel; insured losses fall on CMHC/insurers | LTV 70–90% sensitivity |
| 12 | Balance sheet | Static (jump-off loans), RWA migration +0.5–1%/q | Standard in supervisory stress tests | Dynamic balance sheet |
| 13 | Out-of-scope PCL | Non-Canadian PCL held at trailing 4q run rate | PPNR is total-bank; avoids setting it against Canadian losses only | Scale PPNR to Canadian share |
| 14 | Dividends | Held at trailing level through the stress | Conservative (CCAR convention); OSFI could restrict them as in 2020 | No dividends |
| 15 | OSFI threshold | 11.5% = 4.5% min + 2.5% CCB + 1% D-SIB + 3.5% DSB | Current D-SIB expectation; check latest DSB setting | 8.0% hard floor also reported |
| 16 | Headline method | Average of regression and Vasicek | Two independent methods per PRD; ranking reported under each | — |
| 17 | RBC performing (Stage 1–2) PCL | Not disclosed by product × geography. Total-bank Retail / Wholesale Stage 1–2 PCL × Canada's share of retail / wholesale loans; Canadian retail amount split across products by each product's share of trailing-4Q Canadian Stage 3 PCL | Stage 3 PCL and loans are disclosed directly for Canada by product; this is the least arbitrary split available | Split by loan share (puts ~75% on mortgages, too much); or model Stage 3 only (`pcl_imp_bps`) |
| 18 | RBC series breaks | Kept as reported; flagged by validator | Wholesale −22% in FQ4 2019 (geography reclass); small business ×2 in FQ2 2021 (reclass from wholesale); HSBC Canada +27% business, +9% mortgages in FQ2 2024 | Add acquisition dummies if regression residuals spike |
