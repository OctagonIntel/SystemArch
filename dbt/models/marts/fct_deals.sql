select
    d.deal_id,
    d.customer_id,
    c.region,
    d.owner_id,
    d.amount_eur,
    d.stage,
    d.created_at,
    d.close_date
from {{ ref('stg_crm__deals') }} d
join {{ ref('stg_crm__customers') }} c using (customer_id)
