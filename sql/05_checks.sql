-- Each row is a named check; build fails if any returns failing_rows > 0.
create or replace table mart.dq_checks as
select 'fct_budget_line rows = raw rows' as check_name,
       abs((select count(*) from mart.fct_budget_line) - (select count(*) from raw.expense_budget)) as failing_rows
union all
select 'every publication mapped to a stage',
       (select count(*) from mart.dim_budget_stage where stage is null)
union all
select 'one Adopted publication per FY',
       (select count(*) from (select fiscal_year from mart.dim_budget_stage where stage = 'Adopted' group by 1 having count(*) <> 1))
union all
select 'restated prior-FY adopted = that FY''s Adopted plan (within $1)',
       (select count(*) from mart.fy_lifecycle where adopted is not null and adopted_restated is not null
          and abs(adopted - adopted_restated) > 1)
union all
select 'funding total = budget total per publication (within 0.5%)',
       (select count(*) from (
           select f.stage_key, sum(f.amount) fa from mart.v_funding f
           where measure = 'financial_plan' group by 1) x
        join (select stage_key, sum(plan_amount) ba from mart.fct_budget_line group by 1) y using (stage_key)
        where abs(fa / ba - 1) > 0.005)
union all
select 'agencies unique', (select count(*) - count(distinct agency_number) from mart.dim_agency)
union all
select 'no orphan unit of appropriation',
       (select count(*) from mart.fct_budget_line f anti join mart.dim_unit_appropriation u using (ua_key));
