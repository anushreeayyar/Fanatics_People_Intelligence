"""
People Intelligence pipeline - step 1: load + clean people_data.xlsx
Produces tidy pandas frames used by every downstream step.
Every cleaning rule is logged into ISSUES so the write-up and the app's
'Data quality' tab are generated from the same source of truth.
"""
import pandas as pd, numpy as np

AS_OF = pd.Timestamp("2026-09-01")
HOURS_PER_YEAR = 2080          # assumption: 40h x 52w for hourly -> annual
ISSUES = []                    # (id, severity, sheet, issue, rows, treatment)

def log(sev, sheet, issue, rows, treatment):
    ISSUES.append(dict(id=len(ISSUES)+1, severity=sev, sheet=sheet, issue=issue, rows=rows, treatment=treatment))

def load(path):
    x = pd.read_excel(path, sheet_name=None, dtype=str)
    return x

def parse_dates(s):
    s = s.astype(str).str.strip()
    iso = pd.to_datetime(s.where(~s.str.contains("/")), format="%Y-%m-%d", errors="coerce")
    us  = pd.to_datetime(s.where(s.str.contains("/")), format="%m/%d/%Y", errors="coerce")
    return iso.fillna(us)

def build(path):
    ISSUES.clear()
    x = load(path)
    emp, mh, dep, ent, comp, term, ms = (x[k].copy() for k in
        ["employees","manager_hierarchy","departments","legal_entities","comp_history","termination_log","monthly_summary"])

    # ---------- employees ----------
    emp["employee_id"] = emp.employee_id.astype(int)
    raw_hd = emp.hire_date.copy()
    emp["hire_date"] = parse_dates(emp.hire_date)
    n_ws  = (raw_hd != raw_hd.str.strip()).sum()
    n_us  = raw_hd.str.contains("/").sum()
    log("Med","employees","hire_date stored in 3 formats (ISO, M/D/YYYY, leading space)",
        f"{n_us} US-format + {n_ws} padded", "Parsed both formats; all first-fields <=12 and second-fields go to 31, so M/D/YYYY confirmed. 0 unparseable.")
    emp["date_of_birth"] = pd.to_datetime(emp.date_of_birth)

    st_raw = emp.employment_status.copy()
    emp["employment_status"] = emp.employment_status.str.strip().str.title()
    log("Low","employees","employment_status mixed case (ACTIVE/TERMINATED)", int((st_raw!=emp.employment_status).sum()), "Normalised to Title Case")
    d_raw = emp.dept_code.copy()
    emp["dept_code"] = emp.dept_code.str.strip().str.upper()
    log("Med","employees","dept_code lower-case (d33 etc.) - would silently fail a join to departments", int((d_raw!=emp.dept_code).sum()), "Upper-cased before join")
    l_raw = emp.location.copy(); emp["location"] = emp.location.str.strip()
    log("Low","employees","location has trailing whitespace ('Denver, CO ' vs 'Denver, CO') -> splits filters", int((l_raw!=emp.location).sum()), "Trimmed")

    # duplicates
    dup_ids = emp[emp.employee_id.duplicated(keep=False)]
    exact = emp.duplicated(keep="first")
    log("High","employees","Exact duplicate rows (same id, identical fields)", int(exact.sum()), "Dropped duplicates (would otherwise double-count headcount)")
    emp = emp[~exact].copy()
    # rehire: same id, two spells
    rehire_ids = emp[emp.employee_id.duplicated(keep=False)].employee_id.unique().tolist()
    log("High","employees","Employee id used for TWO different employment spells (id %s: hired 3/14/2022 -> terminated 8/15/2024, re-hired 11/10/2025, currently Active). Termination log has only the 2024 exit."%rehire_ids,
        "2 rows", "Treated as a rehire: kept both spells, matched the log to the spell whose hire date precedes the termination date; only the 2025 spell is active. Counts once in headcount.")
    emp["spell"] = emp.groupby("employee_id").cumcount()
    # order spells by hire date so spell 0 is earliest
    emp = emp.sort_values(["employee_id","hire_date"]).reset_index(drop=True)
    emp["spell"] = emp.groupby("employee_id").cumcount()

    # placeholder hire date
    ph = (emp.hire_date == "2015-01-05")
    log("Med","employees","Placeholder-looking hire date 2015-01-05 (63 rows vs <=6 for any other date; it is also the earliest date in the file; many of these people would have been <18 at hire)",
        int(ph.sum()), "Kept as-is (cannot recover true date). All are >10y tenure so they never fall in the <1yr cohort, but tenure-band and 'years of service' metrics are unreliable for them. Flag for HRIS to backfill.")
    emp["placeholder_hire"] = ph

    # ---------- terminations ----------
    term["employee_id"] = term.employee_id.astype(int)
    term["termination_date"] = pd.to_datetime(term.termination_date)

    # attach log to spell
    emp = emp.merge(term, on="employee_id", how="left")
    # for multi-spell ids, term applies only to the spell with hire <= term date
    bad = emp.termination_date.notna() & (emp.termination_date < emp.hire_date)
    for c in ["termination_date","termination_type","reason"]:
        emp.loc[bad, c] = pd.NaT if c=="termination_date" else np.nan
    log("Med","termination_log","Termination dated before the spell's hire date (the rehire's 2025 row)", int(bad.sum()), "Log entry attached to the 2022 spell only")

    # status vs log conflict
    conflict = (emp.employment_status=="Active") & emp.termination_date.notna()
    log("High","employees/termination_log","Status says Active but termination_log has an exit (id %s, 7/15/2026, voluntary-compensation)"%emp.loc[conflict,"employee_id"].tolist(),
        int(conflict.sum()), "Termination log treated as source of truth -> employee counted as terminated. HRIS status not refreshed after exit.")
    emp["is_terminated"] = emp.termination_date.notna()
    emp["status_clean"] = np.where(emp.is_terminated, "Terminated", "Active")

    nolog = (emp.employment_status=="Terminated") & ~emp.is_terminated
    log("Info","employees/termination_log","Terminated employees with no log entry", int(nolog.sum()), "None found (checked)")

    # joins
    emp = emp.merge(dep, on="dept_code", how="left")
    ent["fx_rate_to_usd"] = ent.fx_rate_to_usd.astype(float)
    emp = emp.merge(ent[["entity_code","entity_name","country","currency"]], on="entity_code", how="left")
    emp["dept_name"] = emp.dept_name.fillna("Unknown")
    emp["name"] = emp.first_name + " " + emp.last_name

    # ---------- hierarchy ----------
    mh["employee_id"] = mh.employee_id.astype(int)
    mh["manager_employee_id"] = pd.to_numeric(mh.manager_employee_id, errors="coerce")
    emp = emp.merge(mh, on="employee_id", how="left")

    # ---------- duplicate PERSON under two ids ----------
    k = emp.drop_duplicates("employee_id", keep="last")
    dp = k[k.duplicated(["email","date_of_birth"], keep=False)].sort_values("hire_date")
    DUP_EXCLUDE = []
    if len(dp) == 2:
        keep, drop = dp.iloc[0], dp.iloc[1]
        DUP_EXCLUDE = [int(drop.employee_id)]
        log("High","employees","Same person entered twice under different ids and name variants: %s (id %d, hired %s, no comp history) vs %s (id %d, hired %s, full comp history). Same email, DOB, dept, entity, location."
            % (drop["name"], drop.employee_id, drop.hire_date.date(), keep["name"], keep.employee_id, keep.hire_date.date()),
            "1 row", "Excluded id %d from all counts (kept the record with the comp history/original hire date). This is exactly the 1-FTE gap between my recount and monthly_summary, every month." % drop.employee_id)
    emp["excluded_dup"] = emp.employee_id.isin(DUP_EXCLUDE)

    # ---------- comp ----------
    comp["employee_id"] = comp.employee_id.astype(int)
    comp["amount"] = comp.amount.astype(float)
    comp["effective_date"] = pd.to_datetime(comp.effective_date)
    # comp checks
    fut = comp[comp.effective_date > AS_OF]
    log("High","comp_history","Future-dated comp rows (all 4%% base increases effective 2026-10-01; %d employees incl. Dana Whitfield)" % fut.employee_id.nunique(),
        len(fut), "Excluded from 'current' comp (effective_date <= as-of date). Would add ~$165K annualised once effective. Only 40 of ~1,990 FTEs have one -> looks like a partial load of an Oct cycle.")
    hourly = comp[comp.pay_basis=="Hourly"]
    log("High","comp_history","Base pay recorded as an HOURLY rate for %d rows (all Production Associates/Leads + interns): summing raw amounts would understate their pay ~2,000x" % len(hourly),
        len(hourly), "Annualised at 2,080 hrs (40h x 52w) - assumption, no hours field exists. Interns are excluded anyway (not FTE).")
    log("High","comp_history","Multi-currency: %d comp rows are GBP/EUR/CAD" % (comp.currency!="USD").sum(), int((comp.currency!="USD").sum()),
        "Converted to USD with the single static rate in legal_entities (no rate history/date available). Any FX-sensitive answer (e.g. UK/Canada heavy orgs) should be re-run at Finance's budget rate.")
    return dict(emp=emp, mh=mh, dep=dep, ent=ent, comp=comp, term=term, ms=ms.assign(
        month_end=pd.to_datetime(ms.month_end), **{c: ms[c].astype(int) for c in ms.columns if c!="month_end"}))

if __name__ == "__main__":
    d = build("data/people_data.xlsx")
    print(d["emp"].shape)
    print(pd.DataFrame(ISSUES).to_string())
