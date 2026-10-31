create schema if not exists mart;

-- Budget stage: within each fiscal year, the June publication is the Adopted budget; the others are
-- the Preliminary (Jan/Feb) and Executive (Apr/May) financial plans. FY2017 has no Preliminary on the portal.
create or replace table mart.dim_budget_stage as
with pubs as (select distinct fiscal_year, publication_date from stg.budget_line)
select
    fiscal_year, publication_date,
    case when month(publication_date) = 6 then 'Adopted'
         when month(publication_date) in (4, 5) then 'Executive'
         when month(publication_date) in (1, 2, 3) then 'Preliminary' end as stage,
    case when month(publication_date) = 6 then 3 when month(publication_date) in (4, 5) then 2 else 1 end as stage_order,
    fiscal_year::varchar || '-' || case when month(publication_date) = 6 then 'ADO'
         when month(publication_date) in (4, 5) then 'EXE' else 'PRE' end as stage_key
from pubs;

create or replace table mart.dim_fiscal_year as
select distinct fiscal_year,
       make_date(fiscal_year - 1, 7, 1) as fy_start, make_date(fiscal_year, 6, 30) as fy_end
from stg.budget_line;

-- latest name wins for agencies / units of appropriation renamed over time
create or replace table mart.dim_agency as
select agency_number, arg_max(agency_name, publication_date) as agency_name,
       min(fiscal_year) as first_fy, max(fiscal_year) as last_fy
from stg.budget_line group by 1;

create or replace table mart.dim_unit_appropriation as
select agency_number || '-' || ua_number as ua_key, agency_number, ua_number,
       arg_max(ua_name, publication_date) as ua_name, arg_max(ps_otps, publication_date) as ps_otps
from stg.budget_line group by 1, 2, 3;

create or replace table mart.dim_object_class as
select object_class_number, arg_max(object_class_name, publication_date) as object_class_name
from stg.budget_line group by 1;

create or replace table mart.dim_funding_source as
select * from (values
    ('city', 'City funds', 'City'), ('federal_funds', 'Federal', 'Non-city'),
    ('state_funds', 'State', 'Non-city'), ('inter_fund_agreement_funds', 'Inter-fund agreement (IFA)', 'Non-city'),
    ('intra_city_sales_funds', 'Intra-city sales', 'Non-city'),
    ('other_categorical_funds', 'Other categorical', 'Non-city'),
    ('community_development_funds', 'Community development', 'Non-city')
) t(funding_source_key, funding_source_name, funding_group);
