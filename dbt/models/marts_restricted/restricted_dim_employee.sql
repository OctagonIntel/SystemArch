{{ config(alias='dim_employee') }}
-- Clear-text employees. Readable only through column grants by clearance (ADR-005, ADR-013).
-- marts.dim_employee is the hashed copy everyone else uses.

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
