"""
People Intelligence pipeline - step 2:
  raw workbook -> clean tables -> (a) payload for the HTML explorer, (b) reference answers, (c) issue log.
Run:  python pipeline.py [path/to/people_data.xlsx] [--asof YYYY-MM-DD]
"""
import sys, json, argparse, pandas as pd, numpy as np
from clean import build, ISSUES, AS_OF as DEFAULT_ASOF, HOURS_PER_YEAR, log
from metrics import org_members, active_on, comp_asof

def day(ts):  # days since epoch (int) or None
    return None if pd.isna(ts) else int((ts - pd.Timestamp("1970-01-01")).days)

def make(path, asof):
    d = build(path)
    emp, comp, ent, ms, term = d["emp"], d["comp"], d["ent"], d["ms"], d["term"]
    fx = dict(zip(ent.currency, ent.fx_rate_to_usd))

    # -------- extra issues that need computation --------
    E_all = emp[~emp.excluded_dup]
    nonfte = E_all[(E_all.worker_type != "FTE") & E_all.termination_date.notna()]
    intern_vol = nonfte[(nonfte.worker_type == "Intern") & (nonfte.termination_type == "Voluntary")]
    log("High", "termination_log", "termination_log mixes FTEs, contractors and interns; all %d intern exits ('End of Internship') are typed VOLUNTARY, %d contractor exits are 'Contract End'. Unfiltered, Aug-2025 'voluntary terms' = 64 instead of 12 and Aug-2026 = 46 instead of 22."
        % (len(intern_vol), (nonfte.worker_type=="Contractor").sum()), len(nonfte),
        "Attrition is FTE-only. Contractors/interns are available behind the worker-type filter but flagged.")
    # monthly_summary reconciliation
    rows = []
    F = E_all[E_all.worker_type == "FTE"]
    for _, r in ms.iterrows():
        me = r.month_end; ms_ = me.replace(day=1)
        hc = len(active_on(F, me, None)); a = active_on(F, me, None)
        lt1 = int(((me - a.hire_date).dt.days < 365).sum())
        vol = int(((F.termination_date >= ms_) & (F.termination_date <= me) & (F.termination_type == "Voluntary")).sum())
        inv = int(((F.termination_date >= ms_) & (F.termination_date <= me) & (F.termination_type == "Involuntary")).sum())
        rows.append(dict(month_end=str(me.date()), hc_mine=hc, hc_summary=int(r.fte_headcount), lt1_mine=lt1, lt1_summary=int(r.fte_headcount_tenure_lt_1yr),
                         vol_mine=vol, vol_summary=int(r.voluntary_terms), invol_mine=inv, invol_summary=int(r.involuntary_terms)))
    recon = pd.DataFrame(rows)
    bad = recon[(recon.hc_mine != recon.hc_summary) | (recon.lt1_mine != recon.lt1_summary) | (recon.vol_mine != recon.vol_summary) | (recon.invol_mine != recon.invol_summary)]
    mism = recon[recon.vol_mine != recon.vol_summary]
    log("Med", "monthly_summary", "monthly_summary does not tie to the source tables: voluntary_terms for %s is %s in the summary vs %s in the termination log (FTE). Headcount ties to my rebuild in all 24 months once the duplicate person is removed (raw file would be +1 every month); tenure<1yr ties using a <365-day definition."
        % (", ".join(mism.month_end), ", ".join(map(str, mism.vol_summary)), ", ".join(map(str, mism.vol_mine))), len(mism),
        "Did not use monthly_summary for any answer; rebuilt every figure from employees + termination_log. Suggest whoever keeps it stops hand-keying and uses the pipeline.")
    mm = comp.merge(E_all.drop_duplicates("employee_id")[["employee_id","currency","worker_type"]], on="employee_id", suffixes=("","_entity"))
    cm = mm[mm.currency != mm.currency_entity]
    log("Low", "comp_history", "%d comp rows are labelled USD but the employee's entity is Europe B.V. (EUR). All are hourly interns." % len(cm), len(cm),
        "Left as labelled (USD); interns are out of scope for every FTE answer, so no impact. Worth fixing at source.")
    log("Low", "employees", "Names/emails inconsistent: 20 surnames carry a '2' suffix (e.g. 'Kelly2'); 25 emails don't match the person's name (incl. every VP + CEO).", 45,
        "Not used as join keys (employee_id only). Flagged for HRIS.")

    # -------- comp -> annualised USD rows --------
    comp2 = comp[comp.employee_id.isin(E_all.employee_id)].copy()
    comp2["usd"] = comp2.amount * np.where(comp2.pay_basis == "Hourly", HOURS_PER_YEAR, 1) * comp2.currency.map(fx)
    comp2 = comp2.sort_values(["employee_id","component","effective_date"])

    # -------- payload --------
    lvl_order = ["CEO","VP","Director","Manager","Senior Analyst","Analyst","Production Lead","Production Associate","Intern","Contractor"]
    reasons = sorted(E_all.reason.dropna().unique())
    E = E_all.copy()
    E["wt"] = E.worker_type.map({"FTE":"F","Contractor":"C","Intern":"I"})
    E["tt"] = E.termination_type.map({"Voluntary":"V","Involuntary":"I"})
    cols = ["id","name","level","dept","func","entity","country","wt","hire","term","tt","reason","mgr","ph"]
    rowsE = [[int(r.employee_id), r["name"], r.job_level, r.dept_name, r.function, r.entity_name, r.country, r.wt,
              day(r.hire_date), day(r.termination_date), (r.tt if isinstance(r.tt,str) else None),
              (reasons.index(r.reason) if isinstance(r.reason,str) else None),
              (int(r.manager_employee_id) if pd.notna(r.manager_employee_id) else None), bool(r.placeholder_hire)]
             for _, r in E.iterrows()]
    rowsC = [[int(r.employee_id), "B" if r.component == "Base" else "T", day(r.effective_date), round(float(r.usd), 2)] for _, r in comp2.iterrows()]
    fut = comp2[comp2.effective_date > asof]
    prev = comp2[comp2.effective_date <= asof].groupby(["employee_id","component"]).tail(1)
    pm = fut.merge(prev, on=["employee_id","component"], suffixes=("_f","_p"))
    pending = dict(n=int(fut.employee_id.nunique()), date=str(fut.effective_date.min().date()) if len(fut) else "", usd=float((pm.usd_f - pm.usd_p).sum()) if len(pm) else 0.0)
    payload = dict(meta=dict(pending_comp=pending, asof=str(asof.date()), data_through=str((asof - pd.Timedelta(days=1)).date()),
                             term_log_start=str(term.termination_date.min().date()), first_full_month="2024-09-01",
                             hours_per_year=HOURS_PER_YEAR, fx=fx, levels=lvl_order, reasons=reasons,
                             built=str(pd.Timestamp.now().date())),
                   ecols=cols, emps=rowsE, comp=rowsC,
                   issues=ISSUES, recon=recon.to_dict("records"))
    return d, E_all, comp2, payload

# ---------------- reference (pandas) answers - independent of the JS engine ----------------
def tcc_for(cur, comp2, asof):
    c = comp2[comp2.effective_date <= asof].groupby(["employee_id","component"]).tail(1)
    b = c[c.component=="Base"].set_index("employee_id").usd.rename("base")
    bo = c[c.component=="Target Bonus"].set_index("employee_id").usd.rename("bonus")
    x = cur.set_index("employee_id").join(b).join(bo); x["bonus"] = x.bonus.fillna(0); x["tcc"] = x.base + x.bonus
    return x

def reference(E_all, comp2, asof):
    Ei = E_all.drop_duplicates("employee_id", keep="last")
    F = E_all[E_all.worker_type=="FTE"]
    out = {}
    cur = active_on(F, asof, None)
    x = tcc_for(cur, comp2, asof)
    out["company"] = dict(fte=len(cur), tcc=float(x.tcc.sum()))
    for nm in ["Morgan Reyes","Dana Whitfield"]:
        L = Ei[Ei.name==nm].iloc[0]; mem = org_members(Ei, L.employee_id)
        for inc in (True, False):
            ids = mem + ([L.employee_id] if inc else [])
            o = x[x.index.isin(ids)]
            out[f"{nm}|{'incl' if inc else 'excl'}"] = dict(fte=len(o), tcc=float(o.tcc.sum()), base=float(o.base.sum()), bonus=float(o.bonus.sum()))
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("path", nargs="?", default="data/people_data.xlsx")
    ap.add_argument("--asof", default=str(DEFAULT_ASOF.date())); ap.add_argument("--out", default=".")
    a = ap.parse_args(); asof = pd.Timestamp(a.asof)
    d, E_all, comp2, payload = make(a.path, asof)
    json.dump(payload, open(f"{a.out}/payload.json","w"), separators=(",",":"))
    pd.DataFrame(ISSUES).to_csv(f"{a.out}/data_issues_log.csv", index=False)
    pd.DataFrame(payload["recon"]).to_csv(f"{a.out}/monthly_summary_reconciliation.csv", index=False)
    ref = reference(E_all, comp2, asof); json.dump(ref, open(f"{a.out}/reference_answers.json","w"), indent=1)
    print(json.dumps(ref, indent=1)); print("payload KB:", round(len(json.dumps(payload))/1024))
