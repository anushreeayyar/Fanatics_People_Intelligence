import sqlite3, json, pandas as pd
import sys, os; sys.path.insert(0, os.getcwd())
from pipeline import make
d, E_all, comp2, payload = make("data/people_data.xlsx", pd.Timestamp("2026-09-01"))
e = E_all.copy()
for c in ["hire_date","termination_date"]: e[c] = e[c].dt.strftime("%Y-%m-%d")
e = e[["employee_id","name","job_level","dept_name","worker_type","hire_date","termination_date","termination_type","reason","manager_employee_id"]]
c = comp2.rename(columns={"usd":"annual_usd"})[["employee_id","component","effective_date","annual_usd"]].copy(); c["effective_date"] = c.effective_date.dt.strftime("%Y-%m-%d")
con = sqlite3.connect(":memory:"); e.to_sql("employees_clean", con, index=False); c.to_sql("comp_clean", con, index=False)
sql = open("analysis/answers.sql").read().split(";")
q12, q3, q4 = [s.strip() for s in sql if s.strip() and not s.strip().startswith("--") or "SELECT" in s][:3] if False else (None,None,None)
blocks = [b.strip() for b in sql if "SELECT" in b]
ref = json.load(open("reference_answers.json")); ok = True
for nm, lid in [("Morgan Reyes",12866),("Dana Whitfield",10474)]:
    for inc in (1,0):
        r = con.execute(blocks[0], dict(leader_id=lid, asof="2026-09-01", include_leader=inc)).fetchone()
        exp = ref[f"{nm}|{'incl' if inc else 'excl'}"]; good = r[0]==exp["fte"] and abs(r[1]-exp["tcc"])<1
        ok &= good; print(("PASS" if good else "FAIL"), nm, "incl" if inc else "excl", r, "expected", exp["fte"], round(exp["tcc"],2))
print("Q3 month-end FTE headcount:", [(m, con.execute(blocks[1], dict(d=m)).fetchone()[0]) for m in ["2025-12-31","2026-01-31","2026-02-28","2026-03-31","2026-04-30","2026-05-31","2026-06-30","2026-07-31","2026-08-31"]])
print("Q4 voluntary FTE exits by quarter:", con.execute(blocks[2]).fetchall())
print("ALL SQL CHECKS PASS" if ok else "SQL CHECK FAILED")
