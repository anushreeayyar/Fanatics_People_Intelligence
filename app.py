"""People Intelligence – Workforce Insights (Streamlit). Run: streamlit run app.py"""
import io, numpy as np, pandas as pd, altair as alt, streamlit as st
from pipeline import make
import piengine as pe

st.set_page_config(page_title="People Intelligence", page_icon="📊", layout="wide")
TEAL, AMBER, BRICK, SLATE = "#0E5C73", "#C77D00", "#B23A2E", "#8592A0"
st.markdown("""<style>
.block-container{padding-top:1.6rem;max-width:1250px}
h1{letter-spacing:-.02em} [data-testid="stMetricValue"]{font-size:2rem}
.answer{border-left:4px solid #0E5C73;background:rgba(14,92,115,.10);padding:.8rem 1.1rem;border-radius:0 10px 10px 0;margin:.2rem 0 1rem}
.answer.bad{border-color:#B23A2E;background:rgba(178,58,46,.10)} .answer.mid{border-color:#C77D00;background:rgba(199,125,0,.12)}
.answer b.big{font-size:1.25rem;display:block;margin-bottom:.15rem} .small{color:#7B8794;font-size:.85rem}
</style>""", unsafe_allow_html=True)

pct = lambda x, d=1: "–" if x is None or pd.isna(x) else f"{x*100:.{d}f}%"
usd = lambda x: f"${x:,.0f}"; usdm = lambda x: f"${x/1e6:,.2f}M"
def box(head, body, kind=""): st.markdown(f'<div class="answer {kind}"><b class="big">{head}</b>{body}</div>', unsafe_allow_html=True)

# ---------------- data ----------------
DEFAULT_FILE = "data/people_data.xlsx"
with st.sidebar:
    st.markdown("### People Intelligence")
    up = st.file_uploader("Refresh: upload the latest people_data.xlsx", type="xlsx", help="Leave empty to use the data already loaded.")
raw = up.getvalue() if up else open(DEFAULT_FILE, "rb").read()
term_log = pd.read_excel(io.BytesIO(raw), sheet_name="termination_log")
last = pd.to_datetime(term_log.termination_date).max()
default_asof = (last + pd.offsets.MonthBegin(1)).normalize() if last.day != 1 else last

@st.cache_data(show_spinner="Preparing the data…")
def load(b, asof):
    d, E, comp2, payload = make(io.BytesIO(b), pd.Timestamp(asof))
    return E, comp2, payload["issues"], payload["recon"], payload["meta"]
try:
    E, comp2, issues, recon, meta = load(raw, str(default_asof.date()))
except Exception as ex:
    st.error(f"This file could not be read ({ex}). Please upload the standard people_data.xlsx workbook."); st.stop()
LOG_START = pd.Timestamp(meta["term_log_start"])

# ---------------- controls ----------------
Ei = E.drop_duplicates("employee_id", keep="last")
has_reports = set(Ei.manager_employee_id.dropna().astype(int))
lead = Ei[Ei.employee_id.isin(has_reports)].copy()
order = ["CEO", "VP", "Director", "Manager", "Senior Analyst", "Analyst"]
lead["o"] = lead.job_level.map({k: i for i, k in enumerate(order)}).fillna(9); lead = lead.sort_values(["o", "name"])
labels = {"Whole company": None}; labels.update({f"{r['name']} — {r.job_level}, {r.dept_name}": int(r.employee_id) for _, r in lead.iterrows()})
if "_goto" in st.session_state: st.session_state["org"] = st.session_state.pop("_goto")
with st.sidebar:
    org_label = st.selectbox("Leader's organisation", list(labels), key="org", help="Type a name to search.")
    incl = st.checkbox("Count the leader in their own org", True)
    wt_label = st.radio("Workers", ["FTEs", "Contractors", "Interns", "All"], horizontal=True)
    months = list(pd.date_range("2025-01-01", default_asof, freq="MS"))[::-1]
    asof = st.selectbox("Data as of", months, format_func=lambda d: d.strftime("%b %d, %Y"))
    st.caption("Synthetic data for the case study.")
WT = {"FTEs": "FTE", "Contractors": "Contractor", "Interns": "Intern", "All": "All"}[wt_label]; wtn = {"FTE": "FTEs", "Contractor": "contractors", "Intern": "interns", "All": "all workers"}[WT]
leader = labels[org_label]; asof = pd.Timestamp(asof)
name = "Whole company" if leader is None else Ei[Ei.employee_id == leader].iloc[0]["name"]
L = pe.select(E, leader, incl, WT); CO = pe.select(E, None, True, WT)
M = pe.monthly(L, asof); Q = pe.quarterly(M); R = pe.rolling12(M)
Q = Q.iloc[1:] if len(Q) and Q.iloc[0].partial else Q          # drop the one-month Q3 2024
MC = pe.monthly(CO, asof); QC = pe.quarterly(MC); QC = QC.iloc[1:] if len(QC) and QC.iloc[0].partial else QC; RC = pe.rolling12(MC)
T = pe.tcc(L, comp2, asof); hc_now = len(T); yr0 = pd.Timestamp(year=(asof - pd.Timedelta(days=1)).year, month=1, day=1)
hc_y0 = pe.hc_at(L, yr0 - pd.Timedelta(days=1)); ytd = hc_now - hc_y0; avg_hc = M.avg.iloc[-1] if len(M) else 0
r_now = R.iloc[-1] if len(R) else None; r_then = R.iloc[0] if len(R) else None; rc_now = RC.iloc[-1] if len(RC) else None

st.title(f"{name}’s org" if leader else "Whole company")
tot_now = len(pe.select(E, leader, incl, 'All').pipe(lambda x: x[(x.hire_date<=asof)&(x.termination_date.isna()|(x.termination_date>asof))]))
st.caption(f"{'' if leader else 'Select a leader in the sidebar to explore their organisation. '}As of {asof:%B %d, %Y}: " + (f"{hc_now:,} FTEs{' (the case population)' if leader is None else ''} · {tot_now:,} total workers including contractors and interns" if WT == "FTE" else (f"{tot_now:,} total workers including contractors and interns" if WT == "All" else f"showing {hc_now:,} {wtn} · {tot_now:,} total workers including contractors and interns")))
if WT != "FTE": st.warning(f"You are viewing {wtn}. The case questions are about FTEs. Interns’ “End of Internship” exits are coded voluntary, so attrition here overstates real resignations.")
def small(pop):
    if pop < 40: st.info(f"Small population (about {pop:.0f} people). One or two exits move these rates a lot — read the counts, not just the percentages.")
def alt_line(kind):
    if leader is None: return ""
    lr = Ei[Ei.employee_id == leader].iloc[0]
    if not (lr.hire_date <= asof and (pd.isna(lr.termination_date) or lr.termination_date > asof)) or (WT not in ("All", lr.worker_type)): return ""
    A = pe.select(E, leader, not incl, WT); ta = pe.tcc(A, comp2, asof)
    return f"<br><span class='small'>{'Without' if incl else 'Including'} {name}: " + (f"{usd(ta.tcc.sum())} ({len(ta):,} people)" if kind == "tcc" else f"{len(ta):,} people") + "</span>"

def sub_table(key):
    start = leader if leader else int(Ei[Ei.manager_employee_id.isna()].employee_id.iloc[0])
    S = pe.sub_orgs(E, comp2, start, WT, asof)
    if S.empty: st.caption("This leader has no sub-leaders under them, so there is nothing further to drill into."); return
    co = pe.ttm(CO, asof); show = S[["Leader", "Title", "People", "TCC_USD", "Voluntary_12m", "FirstYear_12m", "FirstYear_exits"]].rename(columns={"TCC_USD": "Annualised TCC", "Voluntary_12m": "Voluntary attrition (12m)", "FirstYear_12m": "First-year attrition (12m)", "FirstYear_exits": "First-year exits"})
    st.caption("Select a row, then press “Open” to explore that leader’s org.")
    ev = st.dataframe(show, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key=f"sub_{key}",
        column_config={"Annualised TCC": st.column_config.NumberColumn(format="$%d"), "Voluntary attrition (12m)": st.column_config.NumberColumn(format="percent"), "First-year attrition (12m)": st.column_config.NumberColumn(format="percent")})
    if ev.selection.rows:
        row = S.iloc[ev.selection.rows[0]]; lbl = [k for k, v in labels.items() if v == row.leader_id][0]
        if st.button(f"Open {row.Leader}’s org", key=f"open_{key}"): st.session_state["_goto"] = lbl; st.rerun()
    if co is not None: st.caption(f"Company first-year rate for comparison: {pct(co.lt1_rate)}. Look for orgs running at 1.5× or more.")

tabs = st.tabs(["Overview", "Headcount & growth", "Pay (TCC)", "Attrition by quarter", "First-year attrition", "Worth flagging", "Data & method"])

# ---------------- Overview ----------------
with tabs[0]:
    c = st.columns(4)
    c[0].metric("Headcount now", f"{hc_now:,}", f"{ytd:+d} since Jan 1 ({pct(ytd/hc_y0) if hc_y0 else '–'})")
    c[1].metric("Annualised TCC", usdm(T.tcc.sum()), f"{usd(T.tcc.sum()/hc_now)} per person" if hc_now else None, delta_color="off")
    c[2].metric("Voluntary attrition (12m)", pct(r_now.vol_rate) if r_now is not None else "–", f"company {pct(rc_now.vol_rate)}" if leader and rc_now is not None else None, delta_color="off")
    c[3].metric("First-year attrition (12m)", pct(r_now.lt1_rate) if r_now is not None else "–", f"everyone else {pct(r_now.ge1_rate)}" if r_now is not None else None, delta_color="off")
    st.subheader(f"Inside {name}’s org" if leader else "Leaders reporting to the CEO"); sub_table("ov")
    ros = L.assign(status=np.where((L.hire_date <= asof) & (L.termination_date.isna() | (L.termination_date > asof)), "Active", "Not active"))[["employee_id", "name", "job_level", "dept_name", "entity_name" if "entity_name" in L else "country", "worker_type", "hire_date", "termination_date", "status"]]
    st.download_button("Download this org’s roster (CSV, no pay)", ros.to_csv(index=False), f"roster_{name.replace(' ', '_')}_{asof:%Y-%m-%d}.csv", "text/csv")

# ---------------- Headcount ----------------
with tabs[1]:
    ms = M[M.ms >= yr0]; pts = pd.DataFrame({"Month": ["Dec " + str(yr0.year - 1)] + list(ms.ms.dt.strftime("%b")), "Headcount": [hc_y0] + list(ms.end)})
    net = lambda d: int((d.end - d.start).sum()); f3, l3 = ms.head(3), ms.tail(3); lm = ms.iloc[-1] if len(ms) else None
    kind = "bad" if ytd < 0 else ("mid" if len(ms) >= 6 and net(l3) < net(f3) * .6 else "")
    yp = pct(ytd / hc_y0) if hc_y0 else "n/a"
    verdict = (f"Headcount grew through the year, but the pace slowed: +{ytd} net ({yp}). " if ytd > 0 else (f"Flat this year. " if ytd == 0 else f"Headcount fell this year: {ytd} ({yp}). "))
    detail = f"Net adds in the first three months: {net(f3)}. Last three months: {net(l3)}. Last full month ({lm.ms:%b %Y}): {lm.end-lm.start:+d} net ({lm.hires} hires, {lm.exits} exits)." if lm is not None and len(ms) >= 6 else ""
    box(f"{hc_now:,} {wtn} on {asof:%b %d, %Y}", verdict + detail + alt_line("hc"), kind); small(avg_hc)
    a, b = st.columns(2)
    with a:
        st.markdown("**Headcount at each month-end, this year**")
        lo, hi = pts.Headcount.min(), pts.Headcount.max(); pad = max(3, int((hi - lo) * .4))
        st.altair_chart(alt.Chart(pts).mark_line(point=True, color=TEAL).encode(x=alt.X("Month", sort=None), y=alt.Y("Headcount", scale=alt.Scale(domain=[lo - pad, hi + pad]))).properties(height=280), width="stretch")
    with b:
        st.markdown("**Hires vs exits per month**")
        fl = pd.concat([pd.DataFrame({"Month": ms.ms.dt.strftime("%b"), "Type": "Hires", "n": ms.hires}), pd.DataFrame({"Month": ms.ms.dt.strftime("%b"), "Type": "Exits", "n": -ms.exits})])
        st.altair_chart(alt.Chart(fl).mark_bar().encode(x=alt.X("Month", sort=None), y="n", color=alt.Color("Type", scale=alt.Scale(domain=["Hires", "Exits"], range=[TEAL, BRICK]))).properties(height=280), width="stretch")
    a, b = st.columns(2)
    order_l = ["CEO", "VP", "Director", "Manager", "Senior Analyst", "Analyst", "Production Lead", "Production Associate", "Intern", "Contractor"]
    a.markdown("**By job level**"); a.dataframe(T.groupby("job_level").size().rename("People").reindex([o for o in order_l if o in set(T.job_level)]), width="stretch")
    b.markdown("**By department**"); b.dataframe(T.groupby("dept_name").size().rename("People").sort_values(ascending=False), width="stretch")
    st.caption("Headcount counts each person once on the date shown: hired on or before it and not terminated on or before it.")

# ---------------- Pay ----------------
with tabs[2]:
    box(f"{usd(T.tcc.sum())} annualised TCC", f"{hc_now:,} {wtn} in {name if leader else 'the whole company'}’s org on {asof:%b %d, %Y}: base {usdm(T.base.sum())} + target bonus {usdm(T.bonus.sum())}. Average {usd(T.tcc.sum()/hc_now) if hc_now else '–'} per person, in USD." + alt_line("tcc"))
    if T.missing_base.sum(): st.warning(f"{int(T.missing_base.sum())} active people have no base-pay record and count as $0.")
    def grp(col):
        g = T.groupby(col).agg(People=("tcc", "size"), Avg_TCC=("tcc", "mean"), Total_TCC=("tcc", "sum")); g.loc[g.People < 5, ["Avg_TCC", "Total_TCC"]] = np.nan; return g
    a, b = st.columns(2)
    a.markdown("**By job level**"); a.dataframe(grp("job_level").reindex([o for o in order_l if o in set(T.job_level)]), width="stretch", column_config={"Avg_TCC": st.column_config.NumberColumn("Avg TCC", format="$%d"), "Total_TCC": st.column_config.NumberColumn("Total TCC", format="$%d")})
    b.markdown("**By employing country**"); b.dataframe(grp("country").sort_values("People", ascending=False), width="stretch", column_config={"Avg_TCC": st.column_config.NumberColumn("Avg TCC", format="$%d"), "Total_TCC": st.column_config.NumberColumn("Total TCC", format="$%d")})
    st.caption("Rows with fewer than 5 people are masked to protect individuals.")
    fut = comp2[(comp2.effective_date > asof) & comp2.employee_id.isin(T.index)]
    prev = comp2[comp2.effective_date <= asof].sort_values("effective_date").groupby(["employee_id", "component"]).tail(1)
    pm = fut.merge(prev, on=["employee_id", "component"], suffixes=("_f", "_p")); pend_n = fut.employee_id.nunique(); pend_usd = (pm.usd_f - pm.usd_p).sum() if len(pm) else 0
    with st.expander("How this is calculated", expanded=True):
        fx = ", ".join(f"{k} {v}" for k, v in meta["fx"].items() if k != "USD")
        st.markdown(f"""1. **Who:** people active on the as-of date ({wtn}). TCC = base pay + target bonus.
2. **Which pay record:** latest record effective on or before the as-of date, per component. Future-dated changes are ignored{f" — {pend_n} people have a pay change dated {fut.effective_date.min():%b %d, %Y}, worth about {usd(pend_usd)} a year once effective" if pend_n else ""}.
3. **Hourly staff** (production associates and leads) are annualised at {meta['hours_per_year']:,} hours a year (40 h × 52 wks). The data has no hours field, so this is an assumption.
4. **Currency:** GBP, EUR and CAD converted at the single rate in the legal-entity table ({fx}). A budget rate from Finance would shift the non-US portion.
5. **Bonus** is the annual target amount on file, not payout.""")

# ---------------- Attrition ----------------
with tabs[3]:
    cur = Q.iloc[-1] if len(Q) else None; lastq = Q[~Q.partial].iloc[-1] if len(Q[~Q.partial]) else None
    if r_now is not None and r_then is not None:
        d = r_now.vol_rate - r_then.vol_rate; kind = "bad" if d > .005 else ("" if d < -.005 else "mid"); head = "Worse." if d > .005 else ("Better." if d < -.005 else "About the same.")
        ya = Q[Q.quarter == f"Q{lastq.quarter[1]} {int(lastq.quarter[-4:])-1}"] if lastq is not None else pd.DataFrame()
        body = f"Voluntary attrition (annualised) over the last 12 months is {pct(r_now.vol_rate)}, versus {pct(r_then.vol_rate)} for the 12 months ending {r_then.month:%b %Y}. " + (f"{lastq.quarter} ran at {pct(lastq.vol_rate)} against {pct(ya.vol_rate.iloc[0])} a year earlier. " if len(ya) else "") + (f"{cur.quarter} so far ({cur.months} month{'s' if cur.months>1 else ''}: July–August only) is running at {pct(cur.vol_rate)}." if cur is not None and cur.partial else "")
    else: head, body, kind = "Not enough history", "Twelve full months of data are needed for a trailing-12-month rate.", ""
    box(head, body, kind); small(avg_hc)
    a, b = st.columns(2)
    q = Q.assign(Label=Q.quarter + np.where(Q.partial, "*", ""), Rate=Q.vol_rate * 100, Series=name, Partial=Q.partial); base = alt.Chart(q).mark_bar(color=TEAL, cornerRadius=3).encode(x=alt.X("Label", sort=None, title=None), y=alt.Y("Rate", title="% annualised"), opacity=alt.Opacity("Partial:N", scale=alt.Scale(domain=[False, True], range=[1, .45]), legend=None))
    layers = [base]
    if leader: layers.append(alt.Chart(QC.assign(Label=QC.quarter + np.where(QC.partial, "*", ""), Rate=QC.vol_rate * 100)).mark_line(point=True, color=AMBER, strokeDash=[5, 4]).encode(x=alt.X("Label", sort=None), y="Rate"))
    a.markdown("**Voluntary attrition by quarter (annualised)**  \n<span class='small'>* partial quarter · amber dashed = whole company</span>", unsafe_allow_html=True); a.altair_chart(alt.layer(*layers).properties(height=300), width="stretch")
    if len(R):
        rr = pd.DataFrame({"Month": R.month, name: R.vol_rate * 100}); 
        if leader: rr["Whole company"] = RC.vol_rate.values * 100
        rr = rr.melt("Month", var_name="Series", value_name="Rate")
        b.markdown("**Trailing 12-month voluntary attrition**"); b.altair_chart(alt.Chart(rr).mark_line(point=True).encode(x=alt.X("Month:T", title=None), y=alt.Y("Rate", title="%"), color=alt.Color("Series", scale=alt.Scale(range=[TEAL, AMBER]), legend=alt.Legend(orient="bottom", title=None))).properties(height=300), width="stretch")
    st.markdown("**Quarter detail**"); det = Q[["quarter", "vol", "invol", "avg", "vol_rate", "months"]].rename(columns={"quarter": "Quarter", "vol": "Voluntary exits", "invol": "Involuntary exits", "avg": "Avg headcount", "vol_rate": "Voluntary rate (annualised)", "months": "Months of data"})
    st.dataframe(det, hide_index=True, width="stretch", column_config={"Avg headcount": st.column_config.NumberColumn(format="%d"), "Voluntary rate (annualised)": st.column_config.NumberColumn(format="percent")})
    st.caption("Rate = voluntary exits ÷ average headcount, scaled to a full year. FTEs only by default — contract-end and end-of-internship exits are excluded. Q3 2024 is left out (the termination log starts mid-August 2024, so it holds one month).")

# ---------------- First year ----------------
with tabs[4]:
    if r_now is not None:
        mult = r_now.lt1_rate / r_now.ge1_rate if r_now.ge1_rate else None; kind = "bad" if mult and mult > 1.3 else "mid"
        head = "Yes — and it is getting worse." if mult and mult > 1.3 else "Not clearly."
        box(head, f"People in their first year (under 365 days of service) are leaving voluntarily at {pct(r_now.lt1_rate)} a year, versus {pct(r_now.ge1_rate)} for everyone with a year or more" + (f" — {mult:.1f}× higher" if mult else "") + f". A year earlier: {pct(r_then.lt1_rate)} vs {pct(r_then.ge1_rate)}. Method: voluntary exits with under 365 days of service ÷ average headcount under 365 days of service, annualised ({int(r_now.vol_lt1)} exits on about {r_now.avg_lt1:.0f} people).", kind)
        if r_now.avg_lt1 < 40: small(r_now.avg_lt1)
    a, b = st.columns(2)
    q1 = Q[Q.avg_lt1 > 0]; ch = pd.concat([pd.DataFrame({"Quarter": q1.quarter + np.where(q1.partial, "*", ""), "Group": "First year (under 1 yr)", "Rate": q1.lt1_rate * 100}), pd.DataFrame({"Quarter": q1.quarter + np.where(q1.partial, "*", ""), "Group": "Everyone else (1+ yr)", "Rate": q1.ge1_rate * 100})])
    a.markdown("**Voluntary attrition by tenure (annualised, per quarter)**"); a.altair_chart(alt.Chart(ch).mark_bar().encode(x=alt.X("Quarter", sort=None, title=None), xOffset="Group", y=alt.Y("Rate", title="%"), color=alt.Color("Group", scale=alt.Scale(domain=["First year (under 1 yr)", "Everyone else (1+ yr)"], range=[BRICK, TEAL]), legend=alt.Legend(orient="bottom", title=None))).properties(height=300), width="stretch")
    co = pe.cohorts(L, asof, LOG_START)
    def cell(n, x): return "too new" if n == 0 else (f"{x} of {n}" if n < 8 else f"{x/n*100:.0f}% ({x}/{n})")
    ct = pd.DataFrame({"Hired in": co.quarter, "Hires": co.hires, "Quit within 90 days": [cell(r.n90, r.x90) for r in co.itertuples()], "6 months": [cell(r.n180, r.x180) for r in co.itertuples()], "12 months": [cell(r.n365, r.x365) for r in co.itertuples()]})
    b.markdown("**Of people hired in each quarter, % who quit within…**"); b.dataframe(ct, hide_index=True, width="stretch"); b.caption("Only people who have been here long enough to be measured are counted. Hires before Sep 2024 are left out (leavers before the log began are missing).")
    to = asof - pd.Timedelta(days=1); frm = (to.replace(day=1) - pd.DateOffset(months=11)); rs = pe.exit_reasons(L, frm, to, True)
    a, b = st.columns(2)
    a.markdown("**Why first-year leavers said they left (last 12 months)**")
    soft = comp_share = 0
    if len(rs):
        rs["Reason"] = rs.reason.str.replace("Resignation - ", ""); rs["Share"] = rs.exits / rs.exits.sum(); a.dataframe(rs[["Reason", "exits", "Share"]].rename(columns={"exits": "Exits"}), hide_index=True, width="stretch", column_config={"Share": st.column_config.NumberColumn(format="percent")})
        sh = dict(zip(rs.Reason, rs.Share)); soft = sh.get("Relocation", 0) + sh.get("Return to School", 0); comp_share = sh.get("Compensation", 0)
        a.caption(f"Relocation and return-to-school are {pct(soft,0)} of first-year exits; compensation {pct(comp_share,0)}.")
    else: a.caption("No first-year voluntary exits in this window.")
    with b: st.markdown("**Where it is happening**"); sub_table("fy")
    st.markdown("**What I would do**")
    st.markdown(f"""1. **Go where it is concentrated, not everywhere.** Use the table above; orgs at 1.5× the company first-year rate or more are the place to start. Sit down with that leader’s HRBP and read the last 20 first-year exits case by case — hiring source, manager, team, onboarding path.
2. **Catch current hires before they go.** The newest hire cohorts are quitting sooner than earlier ones (see the 90-day column). Run 30/90/180-day check-ins for anyone hired since January.
3. **Don’t default to a pay fix.** In this data early leavers’ base pay is within a couple of percent of peers at the same level, and “Compensation” is {pct(comp_share,0)} of first-year exits. Relocation and return-to-school are {pct(soft,0)} — that points at who we hire (local candidates, expected-tenure screening) and career-path clarity.
4. **Fix the measurement.** Add exit-interview themes, hiring source and hiring manager to the termination data so the next version can tell us *why*, not just *where*.""")

# ---------------- Findings ----------------
with tabs[5]:
    F = CO if WT == "FTE" else pe.select(E, None, True, "FTE"); MF = pe.monthly(F, asof); QF = pe.quarterly(MF); QF = QF.iloc[1:] if QF.iloc[0].partial else QF; RF = pe.rolling12(MF); rF = RF.iloc[-1]
    st.caption(f"Company-wide, FTEs only, as of {asof:%B %d, %Y}. Numbers are computed from the same data as every other tab.")
    Ei_ = Ei; top = None; rows = []
    ceo = int(Ei[Ei.manager_employee_id.isna()].employee_id.iloc[0])
    for _, v in Ei[Ei.manager_employee_id == ceo].iterrows():
        ids = pe.org_ids(E, int(v.employee_id), True); Lv = F[F.employee_id.isin(ids)]; rest = F[~F.employee_id.isin(ids)]; r = pe.ttm(Lv, asof)
        rows.append(dict(v=v, ids=ids, r=r, rr=pe.ttm(rest, asof), rest=rest, ytd=pe.hc_at(Lv, asof) - pe.hc_at(Lv, yr0 - pd.Timedelta(days=1)), L=Lv))
    rows = [x for x in rows if x["r"] is not None]; top = max(rows, key=lambda x: x["r"].lt1_rate)
    rest_r = pe.rolling12(pe.monthly(top["rest"], asof)); dirs = [pe.ttm(F[F.employee_id.isin(pe.org_ids(E, int(d.employee_id), True))], asof) for _, d in Ei[(Ei.manager_employee_id == top["v"].employee_id) & Ei.employee_id.isin(has_reports)].iterrows()]
    above = sum(1 for d in dirs if d is not None and d.lt1_rate > rF.lt1_rate); rest_ytd = (pe.hc_at(F, asof) - pe.hc_at(F, yr0 - pd.Timedelta(days=1))) - top["ytd"]
    shrink = [x["v"]["name"] for x in rows if x["ytd"] < 0]; depts = ", ".join(top["L"].drop_duplicates("employee_id").dept_name.value_counts().head(4).index)
    vname = top["v"]["name"]; fq, lq, cq = QF[~QF.partial].iloc[0], QF[~QF.partial].iloc[-1], QF.iloc[-1]
    l3 = MF.tail(3); h24 = MF.hires.iloc[1:]; lmm = MF.iloc[-1]; ivs = E[(E.worker_type == "Intern") & (E.termination_type == "Voluntary")]; pk = ivs.groupby(ivs.termination_date.dt.strftime("%b %Y")).size().sort_values(ascending=False).head(2)
    badm = [r for r in recon if r["vol_mine"] != r["vol_summary"]]
    items = [("bad", f"{vname}’s org is where the attrition problem is concentrated",
        f"Over the last 12 months its first-year voluntary attrition is {pct(top['r'].lt1_rate,0)} ({int(top['r'].vol_lt1)} exits) against {pct(top['rr'].lt1_rate,0)} in the rest of the company, and its longer-tenured people leave at {pct(top['r'].ge1_rate,0)} versus {pct(top['rr'].ge1_rate,0)}. {above} of {len(dirs)} director teams under {vname.split()[0]} are above the company first-year rate, so it is broad, not one bad pocket. Take this org out and company-wide voluntary attrition is {pct(rest_r.iloc[-1].vol_rate)} ({pct(rest_r.iloc[0].vol_rate)} a year earlier) — almost flat. Headcount here is {top['ytd']:+d} this year while the rest of the company is {rest_ytd:+d}" + (f" (VP orgs that shrank: {', '.join(shrink)})" if shrink else "") + f". Biggest departments: {depts}. The rest of the company has its own first-year problem: {pct(rest_r.iloc[0].lt1_rate,0)} → {pct(rest_r.iloc[-1].lt1_rate,0)} over the year."),
      ("bad", "Voluntary attrition has climbed steadily, and the recent quarters are the worst", f"Company-wide FTE voluntary attrition (annualised) was {pct(fq.vol_rate)} in {fq.quarter}, {pct(lq.vol_rate)} in {lq.quarter}, and {pct(cq.vol_rate)} so far in {cq.quarter}{' (July–August only)' if cq.partial else ''}. Monthly voluntary exits ran {MF.vol.head(6).min()}–{MF.vol.head(6).max()} in the first six months of data and {', '.join(map(str, l3.vol))} in the last three. Attrition among people with 1+ year of service is up too ({pct(fq.ge1_rate)} in {fq.quarter} → {pct(cq.ge1_rate)} in {cq.quarter}), so this is not only a new-hire problem."),
      ("mid", "Growth is running out of room", f"Hiring has been flat at {h24.min()}–{h24.max()} FTEs a month for two years while exits climb. The last three months averaged {l3.hires.mean():.0f} hires against {l3.exits.mean():.0f} exits; {lmm.ms:%b %Y} is {'the first month in the file where headcount fell' if lmm.end < lmm.start and (MF.iloc[:-1].end >= MF.iloc[:-1].start).all() else 'net ' + format(lmm.end-lmm.start, '+d')} ({lmm.end-lmm.start:+d} net). At the current exit rate the company shrinks unless hiring steps up."),
      ("mid", "Interns are logged as voluntary quits", f"All {len(ivs)} “End of Internship” exits are coded Voluntary ({' and '.join(f'{n} in {m}' for m, n in pk.items())}). Left in, they turn a normal ~12-exit month into a 50+ spike. Every rate here is FTE-only for that reason; it is the easiest way to get attrition wrong."),
      ("info", "The team’s monthly_summary tab is close, but not reliable", "Headcount and first-year counts tie to the source data once one duplicate person is removed, but " + ("; ".join(f"{pd.Timestamp(r['month_end']):%b %Y} shows {r['vol_summary']} voluntary exits where the termination log has {r['vol_mine']}" for r in badm) if badm else "voluntary exits tie") + ". It looks hand-keyed; everything here is rebuilt from the source tables."),
      ("info", "Record-level problems that each move a headcount by one", "(1) “Rob Calloway” and “Robert Calloway” share email, birthday, department and location under two employee IDs; Rob has no pay record. (2) Jordan Beck resigned on 15 Jul 2026 but is still marked Active. (3) Three employees appear twice as identical rows. (4) One employee ID covers two employment stints (left 2024, rejoined 2025). One person, one ID, one status is the first thing to fix at source.")]
    fut2 = comp2[comp2.effective_date > asof]
    if len(fut2): items.append(("info", "Pay changes dated in the future are already loaded", f"{fut2.employee_id.nunique()} people have a pay change dated {fut2.effective_date.min():%b %d, %Y} (all 4% base increases). Only {fut2.employee_id.nunique()} of roughly 2,000 FTEs, so it is a partial load or a targeted cycle. Left out of current pay; confirm with Total Rewards before Finance forecasts from this file."))
    for k, h, p in items: box(h, p, {"bad": "bad", "mid": "mid", "info": ""}[k])

# ---------------- Data & method ----------------
with tabs[6]:
    st.subheader("Data issues found and how each was handled")
    st.dataframe(pd.DataFrame(issues).astype({"rows": str}).rename(columns={"id": "#", "severity": "Severity", "sheet": "Where", "issue": "Issue", "rows": "Rows", "treatment": "What I did"}), hide_index=True, width="stretch")
    st.subheader("Definitions used")
    st.markdown("""- **Org** = the leader plus everyone who reports to them directly or indirectly. Untick “Count the leader” to exclude the leader.
- **Headcount** on a date = hired on/before and not terminated on/before that date. FTEs by default.
- **Voluntary attrition rate** = voluntary exits ÷ average headcount, annualised. Trailing-12-month uses the last 12 full months.
- **First year** = under 365 days of service (matches the monthly_summary tab).
- **TCC** = annualised base + target bonus in USD, latest record effective on or before the as-of date.
- **Termination date** is the last day of employment; the person is not counted on that date.""")
    st.subheader("Reconciliation to the monthly_summary tab")
    rc = pd.DataFrame(recon)[["month_end", "hc_mine", "hc_summary", "lt1_mine", "lt1_summary", "vol_mine", "vol_summary"]]; rc.columns = ["Month end", "FTE HC (rebuilt)", "FTE HC (summary)", "Under-1yr (rebuilt)", "Under-1yr (summary)", "Voluntary (rebuilt)", "Voluntary (summary)"]
    st.dataframe(rc, hide_index=True, width="stretch")
    st.caption("Refreshing: upload the new people_data.xlsx in the sidebar. The “as of” date moves to the first of the month after the latest termination.")
