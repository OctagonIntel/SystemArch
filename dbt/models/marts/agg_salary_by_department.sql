-- Salary totals, no individuals. Groups smaller than min_group_size are left out,
-- so nobody can read one person's salary off a department of one (dbt_project.yml).
select
    department,
    region,
    count(*)                      as headcount,
    sum(salary_eur)               as total_salary_eur,
    round(avg(salary_eur), 2)     as avg_salary_eur
from {{ ref('stg_hr__employees') }}
group by department, region
having count(*) >= {{ var('min_group_size') }}
