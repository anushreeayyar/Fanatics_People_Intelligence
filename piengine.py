"""Metric engine for the Streamlit app (pandas). Mirrors engine.js; both are tested against the same reference answers."""
import numpy as np, pandas as pd

FIRST_FULL_MONTH = pd.Timestamp("2024-09-01")   # termination_log starts 2024-08-15
FAR = np.datetime64("2262-01-01")

def org_ids(E, leader, include_leader=True):
    """leader + everyone who reports to them directly or indirectly (leader=None -> everyone)."""
    if leader is None: return set(E.employee_id)
    Ei = E.drop_duplicates("employee_id")
    kids = Ei.dropna(subset=["manager_employee_id"]).groupby("manager_employee_id").employee_id.apply(list).to_dict()
    out, stack = set(), [leader]
    while stack:
        for k in kids.get(stack.pop(), []):
            if k not in out: out.add(k); stack.append(k)
    if include_leader: out.add(leader)
    return out

def select(E, leader=None, include_leader=True, wt="FTE"):
    m = E.employee_id.isin(org_ids(E, leader, include_leader))
    if wt != "All": m &= E.worker_type == wt
    return E[m]

def _arr(L):
    h = L.hire_date.values.astype("datetime64[D]"); t = L.termination_date.values.astype("datetime64[D]")
    t = np.where(np.isnat(t), FAR, t).astype("datetime64[D]"); return h, t

def hc_at(L, d, lt1=False):
    h, t = _arr(L); d = np.datetime64(pd.Timestamp(d), "D"); a = (h <= d) & (t > d)
    if lt1: a &= (d - h).astype(int) < 365
    return int(a.sum())

def monthly(L, asof):
    h, t = _arr(L); out = []
    end_month = (pd.Timestamp(asof) - pd.Timedelta(days=1)).replace(day=1)
    for ms in pd.date_range(FIRST_FULL_MONTH, end_month, freq="MS"):
        me = ms + pd.offsets.MonthEnd(0); prev = ms - pd.Timedelta(days=1)
        hire_in = (h >= np.datetime64(ms, "D")) & (h <= np.datetime64(me, "D"))
        ex = (t >= np.datetime64(ms, "D")) & (t <= np.datetime64(me, "D"))
        ten = (t - h).astype(int); v = (L.termination_type.values == "Voluntary")
        m = dict(ms=ms, label=ms.strftime("%Y-%m"), start=hc_at(L, prev), end=hc_at(L, me), lt1s=hc_at(L, prev, True), lt1e=hc_at(L, me, True),
                 hires=int(hire_in.sum()), exits=int(ex.sum()), vol=int((ex & v).sum()), invol=int((ex & ~v).sum()),
                 vol_lt1=int((ex & v & (ten < 365)).sum()), vol_ge1=int((ex & v & (ten >= 365)).sum()))
        m["avg"] = (m["start"] + m["end"]) / 2; m["avg_lt1"] = (m["lt1s"] + m["lt1e"]) / 2; m["avg_ge1"] = m["avg"] - m["avg_lt1"]
        out.append(m)
    return pd.DataFrame(out)

def _rate(n, pop, months): return (n / pop) * (12 / months) if pop > 0 else np.nan

def quarterly(M):
    if M.empty: return M
    M = M.assign(q=M.ms.dt.to_period("Q")); rows = []
    for q, g in M.groupby("q"):
        n = len(g); d = dict(quarter=f"Q{q.quarter} {q.year}", months=n, partial=n < 3, hires=g.hires.sum(), exits=g.exits.sum(),
            vol=g.vol.sum(), invol=g.invol.sum(), vol_lt1=g.vol_lt1.sum(), vol_ge1=g.vol_ge1.sum(), avg=g.avg.mean(), avg_lt1=g.avg_lt1.mean(), avg_ge1=g.avg_ge1.mean())
        d["vol_rate"] = _rate(d["vol"], d["avg"], n); d["lt1_rate"] = _rate(d["vol_lt1"], d["avg_lt1"], n); d["ge1_rate"] = _rate(d["vol_ge1"], d["avg_ge1"], n)
        rows.append(d)
    return pd.DataFrame(rows)

def rolling12(M):
    rows = []
    for i in range(11, len(M)):
        w = M.iloc[i - 11:i + 1]
        rows.append(dict(month=w.ms.iloc[-1], vol=w.vol.sum(), vol_rate=_rate(w.vol.sum(), w.avg.mean(), 12), vol_lt1=w.vol_lt1.sum(), avg_lt1=w.avg_lt1.mean(),
                         lt1_rate=_rate(w.vol_lt1.sum(), w.avg_lt1.mean(), 12), ge1_rate=_rate(w.vol_ge1.sum(), w.avg_ge1.mean(), 12)))
    return pd.DataFrame(rows)

def ttm(L, asof):
    R = rolling12(monthly(L, asof)); return None if R.empty else R.iloc[-1]

def tcc(L, comp2, asof):
    """annualised base + target bonus (USD) for people active on asof; latest record effective <= asof."""
    asof = pd.Timestamp(asof); act = L[(L.hire_date <= asof) & (L.termination_date.isna() | (L.termination_date > asof))]
    c = comp2[(comp2.employee_id.isin(act.employee_id)) & (comp2.effective_date <= asof)].sort_values("effective_date").groupby(["employee_id", "component"]).tail(1)
    b = c[c.component == "Base"].set_index("employee_id").usd.rename("base"); bo = c[c.component == "Target Bonus"].set_index("employee_id").usd.rename("bonus")
    x = act.drop_duplicates("employee_id", keep="last").set_index("employee_id").join(b).join(bo); x["bonus"] = x.bonus.fillna(0)
    x["missing_base"] = x.base.isna(); x["base"] = x.base.fillna(0); x["tcc"] = x.base + x.bonus
    return x

def cohorts(L, asof, log_start):
    asof = pd.Timestamp(asof); rows = {}
    for _, e in L[(L.hire_date >= log_start) & (L.hire_date <= asof)].iterrows():
        q = e.hire_date.to_period("Q"); r = rows.setdefault(q, dict(quarter=f"Q{q.quarter} {q.year}", hires=0, **{f"n{w}": 0 for w in (90, 180, 365)}, **{f"x{w}": 0 for w in (90, 180, 365)}))
        r["hires"] += 1
        for w in (90, 180, 365):
            if (asof - e.hire_date).days >= w:
                r[f"n{w}"] += 1
                if e.termination_type == "Voluntary" and pd.notna(e.termination_date) and (e.termination_date - e.hire_date).days < w: r[f"x{w}"] += 1
    return pd.DataFrame([rows[k] for k in sorted(rows)])

def exit_reasons(L, start, end, early_only=True):
    x = L[(L.termination_type == "Voluntary") & (L.termination_date >= start) & (L.termination_date <= end)]
    if early_only: x = x[(x.termination_date - x.hire_date).dt.days < 365]
    return x.reason.value_counts().rename_axis("reason").reset_index(name="exits")

def sub_orgs(E, comp2, leader, wt, asof):
    Ei = E.drop_duplicates("employee_id", keep="last"); kids = Ei[Ei.manager_employee_id == leader]
    has = set(Ei.manager_employee_id.dropna()); rows = []
    for _, k in kids[kids.employee_id.isin(has)].iterrows():
        L = select(E, k.employee_id, True, wt); t = tcc(L, comp2, asof); r = ttm(L, asof)
        rows.append(dict(leader_id=int(k.employee_id), Leader=k["name"], Title=f"{k.job_level} · {k.dept_name}", People=len(t), TCC_USD=t.tcc.sum(),
                         Voluntary_12m=None if r is None else r.vol_rate, FirstYear_12m=None if r is None else r.lt1_rate, FirstYear_exits=0 if r is None else int(r.vol_lt1)))
    return pd.DataFrame(rows).sort_values("People", ascending=False) if rows else pd.DataFrame()
