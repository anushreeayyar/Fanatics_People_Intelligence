import json, pandas as pd
import sys, os; sys.path.insert(0, os.getcwd())
from pipeline import make
import piengine as pe
asof = pd.Timestamp("2026-09-01"); d, E, comp2, payload = make("data/people_data.xlsx", asof); ref = json.load(open("reference_answers.json")) if __import__("os").path.exists("reference_answers.json") else None
Ei = E.drop_duplicates("employee_id"); ids = {n: int(Ei[Ei.name == n].employee_id.iloc[0]) for n in ["Morgan Reyes", "Dana Whitfield"]}
ok = True
def chk(l, a, b, tol=1):
    global ok; g = abs(a - b) <= tol; ok &= g; print("PASS" if g else "FAIL", l, a, b)
for n, i in ids.items():
    for inc in (True, False):
        L = pe.select(E, i, inc, "FTE"); t = pe.tcc(L, comp2, asof); chk(f"{n} incl={inc} FTE", len(t), {("Morgan Reyes", True): 418, ("Morgan Reyes", False): 417, ("Dana Whitfield", True): 552, ("Dana Whitfield", False): 551}[(n, inc)], 0)
        if inc and n == "Dana Whitfield": chk("Dana TCC", t.tcc.sum(), 45439575.40)
co = pe.select(E, None, True, "FTE"); M = pe.monthly(co, asof); Q = pe.quarterly(M); R = pe.rolling12(M)
chk("company FTE", pe.hc_at(co, asof), 1991, 0)
exp = {"Q4 2024": .055, "Q1 2025": .076, "Q2 2025": .077, "Q3 2025": .076, "Q4 2025": .071, "Q1 2026": .084, "Q2 2026": .101, "Q3 2026": .124}
for _, r in Q.iterrows():
    if r.quarter in exp: chk(r.quarter + " vol rate", round(r.vol_rate, 3), exp[r.quarter], .0011)
chk("T12M vol", round(R.iloc[-1].vol_rate, 3), .092, .0011); chk("T12M first-year", round(R.iloc[-1].lt1_rate, 3), .275, .0011); chk("T12M 1+yr", round(R.iloc[-1].ge1_rate, 3), .063, .0011); chk("first-year exits", R.iloc[-1].vol_lt1, 74, 0)
print("ALL PASS" if ok else "FAILURES")
