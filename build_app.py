"""One command to refresh: python build_app.py path/to/people_data.xlsx [--asof YYYY-MM-DD]
Re-cleans the workbook, re-runs the reconciliation, and writes the self-contained HTML explorer."""
import sys, json, argparse, pandas as pd
from pipeline import make, reference
from clean import ISSUES
ap = argparse.ArgumentParser(); ap.add_argument("path"); ap.add_argument("--asof", default=None); ap.add_argument("--out", default="People_Intelligence_Explorer.html")
a = ap.parse_args()
if a.asof: asof = pd.Timestamp(a.asof)
else:   # default: first day of the month after the latest termination / hire in the data
    x = pd.read_excel(a.path, sheet_name="termination_log")
    last = pd.to_datetime(x.termination_date).max()
    asof = (last + pd.offsets.MonthBegin(1)).normalize() if last.day != 1 else last
d, E_all, comp2, payload = make(a.path, asof)
here = __import__("os").path.dirname(__file__)
tpl = open(f"{here}/app_template.html").read(); eng = open(f"{here}/engine.js").read()
html = tpl.replace("/*__ENGINE__*/", eng).replace("/*__PAYLOAD__*/", json.dumps(payload, separators=(",",":")))
open(a.out, "w").write(html)
pd.DataFrame(ISSUES).to_csv("data_issues_log.csv", index=False)
print("as-of", asof.date(), "| wrote", a.out, round(len(html)/1024), "KB |", len(ISSUES), "issues logged")
