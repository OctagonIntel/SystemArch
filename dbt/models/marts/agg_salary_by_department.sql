-- Salary totals without individual salaries, for anyone who needs the numbers but not the people.
select
    department,
    region,
    count(*)                      as headcount,
    sum(salary_eur)               as total_salary_eur,
    round(avg(salary_eur), 2)     as avg_salary_eur
from {{ ref('stg_hr__employees') }}
group by department, region
