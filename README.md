# People Intelligence – Workforce Insights

Interactive workforce dashboard for HR Business Partners (Streamlit). Pick a leader, see headcount, pay, attrition and first-year attrition for their org.

**Refreshing:** in the app sidebar, upload the latest `people_data.xlsx`. The view rebuilds itself and moves "as of" to the first of the month after the latest termination. No code, no formulas.

## Run locally
    pip install -r requirements.txt
    streamlit run app.py

## Deploy (Streamlit Community Cloud)
1. Push this repo to GitHub (root = this folder).
2. share.streamlit.io -> New app -> pick the repo, branch `main`, main file `app.py`.
3. Deploy. `data/people_data.xlsx` is the default dataset; replace it (or upload in the sidebar) to refresh.

## Layout
    app.py            the dashboard (what HRBPs use)
    piengine.py       metric engine: org roll-up, headcount, attrition, first-year, cohorts, TCC
    clean.py          cleaning + data-issue log     metrics.py, pipeline.py   shared helpers
    data/             people_data.xlsx (synthetic, as supplied)
    analysis/         answers.sql (SQL re-derivation), data_issues_log.csv, monthly_summary_reconciliation.csv
    docs/             write-up (PDF/Word) and a standalone HTML version of the dashboard
    tests/            run_all.sh - pandas engine vs reference answers, SQL check, HTML engine check, app smoke test
    engine.js, app_template.html, build_app.py   builds docs/People_Intelligence_Explorer.html (no server needed)

Checks: `bash tests/run_all.sh`
