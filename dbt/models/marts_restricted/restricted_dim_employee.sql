{{ config(alias='dim_employee') }}
-- Clear-text employees, columns by clearance. Hashed copy: marts.dim_employee

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
