import pandas as pd, numpy as np
from clean import build, ISSUES, AS_OF, HOURS_PER_YEAR, log

def org_members(emp, leader_id):
    """all direct+indirect reports (recursive), excluding leader"""
    kids = emp.groupby("manager_employee_id").employee_id.apply(list).to_dict()
    out, stack, seen = [], [leader_id], {leader_id}
    while stack:
        for k in kids.get(stack.pop(), []):
            if k not in seen:
                seen.add(k); out.append(k); stack.append(k)
    return out

def active_on(emp, d, worker_type="FTE"):
    m = (emp.hire_date <= d) & (emp.termination_date.isna() | (emp.termination_date > d))
    if worker_type: m &= (emp.worker_type == worker_type)
    return emp[m]

def comp_asof(comp, emp, asof):
    c = comp[comp.effective_date <= asof].sort_values("effective_date")
    latest = c.groupby(["employee_id","component"]).tail(1)
    return latest

if __name__ == "__main__":
    d = build("data/people_data.xlsx")
    emp, comp, ms, ent = d["emp"], d["comp"], d["ms"], d["ent"]
    # cycle check
    par = dict(zip(emp.employee_id, emp.manager_employee_id))
    def depth(i):
        n, seen = 0, set()
        while pd.notna(par.get(i)):
            if i in seen: return -1
            seen.add(i); i = int(par[i]); n += 1
        return n
    emp["depth"] = emp.employee_id.map(depth)
    print(emp.drop_duplicates("employee_id").depth.value_counts().sort_index())
    for nm in ["Morgan Reyes","Dana Whitfield"]:
        L = emp[emp.name==nm].iloc[0]
        mem = org_members(emp.drop_duplicates("employee_id"), L.employee_id)
        cur = active_on(emp, AS_OF)
        print(nm, L.employee_id, "org total ids", len(mem), "| FTE active in org", cur.employee_id.isin(mem).sum(),
              "| incl leader", cur.employee_id.isin(mem+[L.employee_id]).sum())
        sub = emp[emp.employee_id.isin(mem)]
        print(pd.crosstab(sub.worker_type, sub.status_clean))
    print("Company FTE active:", len(active_on(emp, AS_OF)), " (naive Active status FTE:", ((emp.employment_status=="Active")&(emp.worker_type=="FTE")).sum(),")")
    # month-end recompute vs summary
    rows=[]
    for me in ms.month_end:
        f = active_on(emp, me); allw = active_on(emp, me, None)
        lt1 = f[f.hire_date > (me - pd.DateOffset(years=1))]
        mstart = me.replace(day=1); mo = (emp.termination_date>=mstart)&(emp.termination_date<=me)
        t = emp[mo]
        rows.append(dict(month_end=me, fte=len(f), all_workers=len(allw), lt1=len(lt1),
             vol_fte=((t.worker_type=="FTE")&(t.termination_type=="Voluntary")).sum(),
             vol_all=(t.termination_type=="Voluntary").sum(),
             invol_fte=((t.worker_type=="FTE")&(t.termination_type=="Involuntary")).sum(),
             invol_all=(t.termination_type=="Involuntary").sum()))
    r = pd.DataFrame(rows).merge(ms, on="month_end")
    pd.set_option("display.width",250)
    print(r.to_string())
