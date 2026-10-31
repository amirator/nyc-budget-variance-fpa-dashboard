-- Line-level budget fact (one row per source row; 1.1M rows).
create or replace table mart.fct_budget_line as
select l.line_id, s.stage_key, l.fiscal_year, l.publication_date,
       l.agency_number, l.agency_number || '-' || l.ua_number as ua_key, l.object_class_number,
       l.budget_code, l.object_code, l.object_code_name, l.rc_code, l.is_savings_line,
       l.plan_amount, l.prior_fy_adopted_amount, l.prior_fy_modified_amount,
       l.plan_positions, l.prior_fy_adopted_positions, l.prior_fy_modified_positions
from stg.budget_line l join mart.dim_budget_stage s using (fiscal_year, publication_date);

-- Funding fact: unpivot the 7 funding sources x 3 measures to long form.
create or replace table mart.fct_funding as
with u as (
    unpivot stg.funding
    on columns('.*_(financial_plan|adopted_budget|current_budget)_amount$')
    into name col value amount_txt
)
select s.stage_key, u.fiscal_year, u.publication_date, u.agency_number,
       u.agency_number || '-' || u.ua_number as ua_key,
       regexp_replace(col, '_(financial_plan|adopted_budget|current_budget)_amount$', '') as funding_source_key,
       regexp_extract(col, '(financial_plan|adopted_budget|current_budget)', 1) as measure,
       try_cast(amount_txt as double) as amount
from u join mart.dim_budget_stage s using (fiscal_year, publication_date)
where col not like 'total_%';
update mart.fct_funding set funding_source_key = 'city' where funding_source_key = 'city_funds';

-- convenience views: facts with stage attributes (avoids ambiguous fiscal_year/publication_date)
create or replace view mart.v_line as
select f.*, s.stage, s.stage_order from mart.fct_budget_line f join mart.dim_budget_stage s using (stage_key);
create or replace view mart.v_funding as
select f.*, s.stage, s.stage_order from mart.fct_funding f join mart.dim_budget_stage s using (stage_key);
