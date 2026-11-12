{{ config(alias='dim_customer') }}
-- Clear-text customers, columns by clearance, rows by region

select
    customer_id,
    company_name,
    contact_name,
    contact_email,
    contact_phone,
    region,
    country,
    account_owner_id,
    created_at
from {{ ref('stg_crm__customers') }}
