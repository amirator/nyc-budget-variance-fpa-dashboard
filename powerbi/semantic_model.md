# Power BI semantic-model specification

**Status:** a specification plus a DAX measure library (`measures.dax`). **No `.pbix` is included.**
It was built on Linux without Power BI Desktop, so the measures have not been validated in Power BI.
The same calculations are implemented and tested in DuckDB SQL and Python (`sql/`, `tests/`), and the
interactive dashboard in this repo is Plotly HTML (`reports/dashboard.html`).

## Tables (star schema, from `data/fpa.duckdb`, schema `mart`)

| Table | Grain | Key | Rows (Oct 2026 load) |
|---|---|---|---:|
| fct_budget_line | one source budget line per publication | line_id | 1,137,678 |
| fct_funding | publication × unit of appropriation × funding source × measure | (stage_key, ua_key, funding_source_key, measure) | 446,040 |
| dim_budget_stage | fiscal year × publication | stage_key (e.g. `2027-ADO`) | 32 |
| dim_fiscal_year | fiscal year (1 Jul – 30 Jun) | fiscal_year | 11 |
| dim_agency | agency | agency_number | 149 |
| dim_unit_appropriation | agency × unit of appropriation | ua_key | 770 |
| dim_object_class | object class | object_class_number | 19 |
| dim_funding_source | funding source | funding_source_key | 7 |

## Relationships (all single-direction, many-to-one)

```
fct_budget_line[stage_key]           -> dim_budget_stage[stage_key]
fct_budget_line[fiscal_year]         -> dim_fiscal_year[fiscal_year]
fct_budget_line[agency_number]       -> dim_agency[agency_number]
fct_budget_line[ua_key]              -> dim_unit_appropriation[ua_key]
fct_budget_line[object_class_number] -> dim_object_class[object_class_number]
fct_funding[stage_key]               -> dim_budget_stage[stage_key]
fct_funding[fiscal_year]             -> dim_fiscal_year[fiscal_year]
fct_funding[agency_number]           -> dim_agency[agency_number]
fct_funding[ua_key]                  -> dim_unit_appropriation[ua_key]
fct_funding[funding_source_key]      -> dim_funding_source[funding_source_key]
```
`dim_budget_stage[fiscal_year]` should be hidden to avoid ambiguous paths. Use `dim_fiscal_year` for slicing.

## Modelling rules (adapted from the BPA rules in microsoft/Analysis-Services)

* Hide fact-table foreign keys and raw amount columns. Expose measures only.
* Measures live in a dedicated `_Measures` table, in display folders: Base, Stage, Bridge, In-year,
  YoY, Funding, Multi-year.
* Format strings: amounts as `#,0,,,.00 "bn"`, percentages as `0.0%`.
* Use `DIVIDE()` rather than `/` for ratios. Avoid bi-directional relationships. Mark no date table
  (the fiscal year is an integer attribute, and no daily grain exists).
* The in-year measures shift context to FY+1, because the source stores FY N's adopted/modified figures on FY N+1
  rows. This is the main gotcha in the model and is documented in the README.

## Report pages (mirrors reports/dashboard.html)

1. Overview: KPI cards (Adopted, YoY %, in-year revision, CAGR) and a lifecycle line chart.
2. Budget cycle bridge: waterfall of Preliminary → agency deltas → Adopted, with an FY slicer.
3. In-year revisions: waterfall of Adopted → Modified by agency, plus a stacked bar by funding source.
4. Variance decomposition: YoY waterfall by agency and a bar chart by object class.
5. Forecast: imported from `reports/forecast_backtest.csv` (computed in Python).
6. Anomalies: imported from `reports/anomalies_flagged.csv`.
