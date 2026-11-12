-- One row per employee. Holds the most sensitive columns in the warehouse
-- (salary, national ID, date of birth). Who sees what gets decided in Phase 2.
select
    employee_id,
    first_name || ' ' || last_name   as full_name,
    email,
    phone,
    date_of_birth,
    national_id,
    department,
    job_title,
    region,
    country,
    hire_date,
    salary_eur,
    manager_id
from {{ ref('stg_hr__employees') }}
