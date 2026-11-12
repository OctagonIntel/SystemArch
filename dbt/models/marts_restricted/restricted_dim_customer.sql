{{ config(alias='dim_customer') }}
-- Clear-text customers. Column grants by clearance, rows filtered by region.

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
