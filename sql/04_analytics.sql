-- Totals by fiscal year and stage
create or replace table mart.agg_stage_total as
select f.fiscal_year, f.stage, f.stage_order, f.publication_date,
       sum(plan_amount) as plan_amount, sum(plan_positions) as plan_positions, count(*) as n_lines
from mart.v_line f
group by all;

-- Budget lifecycle per FY: Preliminary -> Executive -> Adopted -> final modified.
-- Final modified for FY N is reported as prior_fy_modified in the FY N+1 Adopted publication
-- (as of that June, i.e. at or near the end of FY N).
create or replace table mart.fy_lifecycle as
with st as (
    select fiscal_year,
           max(plan_amount) filter (where stage = 'Preliminary') as preliminary,
           max(plan_amount) filter (where stage = 'Executive') as executive,
           max(plan_amount) filter (where stage = 'Adopted') as adopted
    from mart.agg_stage_total group by 1
),
nxt as (
    select f.fiscal_year - 1 as fiscal_year, sum(prior_fy_adopted_amount) as adopted_restated,
           sum(prior_fy_modified_amount) as modified_latest, max(f.publication_date) as modified_as_of
    from mart.v_line f
    where f.stage = 'Adopted' group by 1
)
select coalesce(st.fiscal_year, nxt.fiscal_year) as fiscal_year, preliminary, executive, adopted,
       adopted_restated, modified_latest, modified_as_of,
       modified_latest - coalesce(adopted, adopted_restated) as in_year_revision,
       (modified_latest / coalesce(adopted, adopted_restated)) - 1 as in_year_revision_pct,
       adopted / preliminary - 1 as prelim_to_adopted_pct
from st full join nxt using (fiscal_year)
order by 1;

-- Agency-level stage amounts (for cycle bridges)
create or replace table mart.agency_stage as
select f.fiscal_year, f.stage, f.agency_number, a.agency_name, sum(plan_amount) as amount
from mart.v_line f
join mart.dim_agency a using (agency_number)
group by all;

-- In-year revision by agency: FY N adopted -> FY N modified, from the FY N+1 Adopted publication
create or replace table mart.agency_in_year_revision as
select f.fiscal_year - 1 as fiscal_year, f.agency_number, a.agency_name,
       sum(prior_fy_adopted_amount) as adopted, sum(prior_fy_modified_amount) as modified,
       sum(prior_fy_modified_amount) - sum(prior_fy_adopted_amount) as revision
from mart.v_line f
join mart.dim_agency a using (agency_number)
where f.stage = 'Adopted' group by all;

-- Year-over-year adopted variance decomposed by agency and by object class
create or replace table mart.yoy_adopted_by_agency as
with a as (select fiscal_year, agency_number, agency_name, amount from mart.agency_stage where stage = 'Adopted')
select cur.fiscal_year, coalesce(cur.agency_number, prv.agency_number) as agency_number,
       coalesce(cur.agency_name, prv.agency_name) as agency_name,
       coalesce(prv.amount, 0) as prior_adopted, coalesce(cur.amount, 0) as adopted,
       coalesce(cur.amount, 0) - coalesce(prv.amount, 0) as variance
from a cur full join a prv on prv.agency_number = cur.agency_number and prv.fiscal_year = cur.fiscal_year - 1
where cur.fiscal_year is not null and cur.fiscal_year > (select min(fiscal_year) from a);

create or replace table mart.yoy_adopted_by_object_class as
with a as (
    select f.fiscal_year, f.object_class_number, sum(plan_amount) amount
    from mart.v_line f
    where f.stage = 'Adopted' group by all
)
select cur.fiscal_year, cur.object_class_number, o.object_class_name,
       coalesce(prv.amount, 0) as prior_adopted, cur.amount as adopted, cur.amount - coalesce(prv.amount, 0) as variance
from a cur left join a prv on prv.object_class_number = cur.object_class_number and prv.fiscal_year = cur.fiscal_year - 1
join mart.dim_object_class o on o.object_class_number = cur.object_class_number
where cur.fiscal_year > (select min(fiscal_year) from a);

-- Funding-source view: adopted plan by source and in-year revision by source
create or replace table mart.funding_source_summary as
with plan as (
    select fiscal_year, funding_source_key, sum(amount) as adopted
    from mart.v_funding f
    where f.stage = 'Adopted' and measure = 'financial_plan' group by all
),
inyr as (
    select fiscal_year - 1 as fiscal_year, funding_source_key,
           sum(amount) filter (where measure = 'adopted_budget') as adopted_restated,
           sum(amount) filter (where measure = 'current_budget') as modified_latest
    from mart.v_funding f
    where f.stage = 'Adopted' group by all
)
select coalesce(p.fiscal_year, i.fiscal_year) as fiscal_year, coalesce(p.funding_source_key, i.funding_source_key) as funding_source_key,
       d.funding_source_name, d.funding_group, p.adopted, i.adopted_restated, i.modified_latest,
       i.modified_latest - i.adopted_restated as in_year_revision
from plan p full join inyr i using (fiscal_year, funding_source_key)
join mart.dim_funding_source d on d.funding_source_key = coalesce(p.funding_source_key, i.funding_source_key);

-- Unit-of-appropriation x object class revision lines (input for anomaly scoring)
create or replace table mart.ua_object_revision as
select f.fiscal_year - 1 as fiscal_year, f.agency_number, a.agency_name, f.ua_key, u.ua_name,
       f.object_class_number, o.object_class_name,
       sum(prior_fy_adopted_amount) as adopted, sum(prior_fy_modified_amount) as modified,
       sum(prior_fy_modified_amount) - sum(prior_fy_adopted_amount) as revision
from mart.v_line f
join mart.dim_agency a using (agency_number)
join mart.dim_unit_appropriation u using (ua_key)
join mart.dim_object_class o using (object_class_number)
where f.stage = 'Adopted' group by all;
