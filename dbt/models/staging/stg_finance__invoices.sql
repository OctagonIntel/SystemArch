with ranked as (
    select *, row_number() over (partition by invoice_id order by _loaded_at desc) as rn
    from {{ source('raw', 'finance_invoices') }}
)

select
    invoice_id,
    invoice_number,
    customer_id,
    invoice_date::date           as invoice_date,
    due_date::date               as due_date,
    amount::numeric(14, 2)       as amount,
    currency,
    status,
    paid_at::date                as paid_at,
    _loaded_at
from ranked
where rn = 1
