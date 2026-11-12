-- Salary totals without individual salaries. This is what finance would get
-- instead of dim_employee, if that's how the Phase 2 decision goes.
select
    department,
    region,
    count(*)                      as headcount,
    sum(salary_eur)               as total_salary_eur,
    round(avg(salary_eur), 2)     as avg_salary_eur
from {{ ref('stg_hr__employees') }}
group by department, region
