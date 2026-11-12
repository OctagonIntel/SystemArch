with ranked as (
    select *, row_number() over (partition by ticket_id order by _loaded_at desc) as rn
    from {{ source('raw', 'support_tickets') }}
)

select
    ticket_id,
    customer_id,
    lower(trim(contact_email))   as contact_email,
    subject,
    priority,
    status,
    opened_at::timestamp         as opened_at,
    closed_at::timestamp         as closed_at,
    agent_id,
    _loaded_at
from ranked
where rn = 1
