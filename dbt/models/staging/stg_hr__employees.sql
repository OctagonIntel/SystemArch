-- Newest version of each employee, typed and cleaned up.
with ranked as (
    select *, row_number() over (partition by employee_id order by _loaded_at desc) as rn
    from {{ source('raw', 'hr_employees') }}
)

select
    employee_id,
    trim(first_name)             as first_name,
    trim(last_name)              as last_name,
    lower(trim(email))           as email,
    trim(phone)                  as phone,
    date_of_birth::date          as date_of_birth,
    national_id,
    department,
    job_title,
    region,
    country,
    hire_date::date              as hire_date,
    salary_eur::numeric(12, 2)   as salary_eur,
    nullif(manager_id, '')       as manager_id,
    _loaded_at
from ranked
where rn = 1
