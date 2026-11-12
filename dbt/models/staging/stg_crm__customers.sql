with ranked as (
    select *, row_number() over (partition by customer_id order by _loaded_at desc) as rn
    from {{ source('raw', 'crm_customers') }}
)

select
    customer_id,
    trim(company_name)           as company_name,
    trim(contact_name)           as contact_name,
    lower(trim(contact_email))   as contact_email,
    trim(contact_phone)          as contact_phone,
    region,
    country,
    account_owner_id,
    created_at::timestamp        as created_at,
    _loaded_at
from ranked
where rn = 1
