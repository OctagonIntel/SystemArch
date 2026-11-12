with ranked as (
    select *, row_number() over (partition by deal_id order by _loaded_at desc) as rn
    from {{ source('raw', 'crm_deals') }}
)

select
    deal_id,
    customer_id,
    owner_id,
    amount_eur::numeric(14, 2)   as amount_eur,
    stage,
    created_at::date             as created_at,
    close_date::date             as close_date,
    _loaded_at
from ranked
where rn = 1
