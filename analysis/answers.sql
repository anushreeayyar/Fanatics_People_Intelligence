-- Independent SQL re-derivation of Q1-Q4 against the CLEANED tables (employees_clean, comp_clean).
-- Run by run_sql_check.py (SQLite). The same logic ports 1:1 to Snowflake.

-- Q1/Q2 :: org roll-up with a recursive CTE, then headcount + TCC as of :asof
-- params: :leader_id, :asof, :include_leader (1/0)
WITH RECURSIVE org(employee_id) AS (
    SELECT employee_id FROM employees_clean WHERE manager_employee_id = :leader_id      -- direct reports
    UNION
    SELECT e.employee_id FROM employees_clean e JOIN org o ON e.manager_employee_id = o.employee_id   -- and everyone below
),
members AS (
    SELECT employee_id FROM org
    UNION SELECT :leader_id WHERE :include_leader = 1
),
active AS (
    SELECT DISTINCT e.employee_id FROM employees_clean e JOIN members USING (employee_id)
    WHERE e.worker_type = 'FTE' AND e.hire_date <= :asof AND (e.termination_date IS NULL OR e.termination_date > :asof)
),
latest AS (               -- latest record per employee+component effective on/before as-of
    SELECT c.* FROM comp_clean c
    WHERE c.effective_date <= :asof
      AND c.effective_date = (SELECT MAX(c2.effective_date) FROM comp_clean c2
                              WHERE c2.employee_id = c.employee_id AND c2.component = c.component AND c2.effective_date <= :asof)
)
SELECT (SELECT COUNT(*) FROM active)                                                    AS fte_headcount,
       ROUND(SUM(l.annual_usd), 2)                                                     AS annualised_tcc_usd
FROM latest l JOIN active a USING (employee_id);

-- Q3 :: month-end FTE headcount, this year
-- (run once per month-end, :d)
SELECT COUNT(*) AS fte_headcount FROM employees_clean
WHERE worker_type = 'FTE' AND hire_date <= :d AND (termination_date IS NULL OR termination_date > :d);

-- Q4 :: voluntary FTE exits per quarter
SELECT strftime('%Y', termination_date) || '-Q' || ((CAST(strftime('%m', termination_date) AS INT) + 2) / 3) AS quarter,
       COUNT(*) AS voluntary_exits
FROM employees_clean
WHERE worker_type = 'FTE' AND termination_type = 'Voluntary' AND termination_date >= '2024-09-01'
GROUP BY 1 ORDER BY 1;
