-- One row per customer. Region drives the row filter for sales later on.
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
