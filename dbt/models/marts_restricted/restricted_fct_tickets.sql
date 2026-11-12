{{ config(alias='fct_tickets') }}
-- Clear-text tickets, so support knows who to reply to

select
    t.ticket_id,
    t.customer_id,
    c.region,
    t.contact_email,
    t.subject,
    t.priority,
    t.status,
    t.opened_at,
    t.closed_at,
    round(extract(epoch from (t.closed_at - t.opened_at)) / 3600.0, 1) as resolution_hours,
    t.agent_id
from {{ ref('stg_support__tickets') }} t
join {{ ref('stg_crm__customers') }} c using (customer_id)
