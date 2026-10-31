-- Typed staging views over raw text columns.
create schema if not exists stg;
create or replace view stg.budget_line as
select
    row_number() over () as line_id,
    strptime(publication_date, '%Y%m%d')::date as publication_date,
    fiscal_year::int as fiscal_year,
    lpad(agency_number, 3, '0') as agency_number, trim(agency_name) as agency_name,
    lpad(unit_appropriation_number, 3, '0') as ua_number, trim(unit_appropriation_name) as ua_name,
    budget_code_number as budget_code, trim(budget_code_name) as budget_code_name,
    lpad(object_class_number, 2, '0') as object_class_number, trim(object_class_name) as object_class_name,
    object_code, trim(object_code_name) as object_code_name,
    responsibility_center_code as rc_code,
    personal_service_other_than_personal_service_indicator as ps_otps,
    financial_plan_savings_flag = 'Y' as is_savings_line,
    coalesce(try_cast(financial_plan_amount as double), 0) as plan_amount,
    coalesce(try_cast(adopted_budget_amount as double), 0) as prior_fy_adopted_amount,
    coalesce(try_cast(current_modified_budget_amount as double), 0) as prior_fy_modified_amount,
    coalesce(try_cast(financial_plan_position as double), 0) as plan_positions,
    coalesce(try_cast(adopted_budget_position as double), 0) as prior_fy_adopted_positions,
    coalesce(try_cast(current_modified_budget_position as double), 0) as prior_fy_modified_positions
from raw.expense_budget;

create or replace view stg.funding as
select
    strptime(publication_date, '%Y%m%d')::date as publication_date,
    fiscal_year::int as fiscal_year,
    lpad(agency_number, 3, '0') as agency_number,
    lpad(unit_appropriation_number, 3, '0') as ua_number,
    personal_service_other_than_personal_service_indicator as ps_otps,
    *
    exclude (publication_date, fiscal_year, agency_number, unit_appropriation_number,
             personal_service_other_than_personal_service_indicator, agency_name, unit_appropriation_name)
from raw.expense_funding;
