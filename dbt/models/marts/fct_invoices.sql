-- Fixed exchange rates keep this simple and repeatable. A real build would use a rates table.
select
    i.invoice_id,
    i.invoice_number,
    i.customer_id,
    c.region,
    i.invoice_date,
    i.due_date,
    i.amount,
    i.currency,
    round(i.amount * case i.currency when 'USD' then 0.92 when 'AUD' then 0.61 else 1 end, 2) as amount_eur,
    i.status,
    i.paid_at,
    i.paid_at - i.invoice_date as days_to_pay
from {{ ref('stg_finance__invoices') }} i
join {{ ref('stg_crm__customers') }} c using (customer_id)
