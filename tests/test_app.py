import sys, os; sys.path.insert(0, os.getcwd())
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("../app.py", default_timeout=180).run()
print("exceptions:", [e.value for e in at.exception]); print("metrics:", [(m.label, m.value) for m in at.metric])
for org in ["Morgan Reyes — VP, Sales", "Dana Whitfield — VP, Manufacturing"]:
    at.selectbox(key="org").set_value(org).run(); print(org, "exc:", [e.value for e in at.exception], [(m.label, m.value) for m in at.metric][:2])
at.radio[0].set_value("Interns").run(); print("interns exc:", [e.value for e in at.exception])
