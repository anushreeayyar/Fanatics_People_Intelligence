#!/bin/bash
# run from repo root
python3 pipeline.py --out . >/dev/null            # writes payload.json + reference_answers.json (git-ignored)
python3 tests/test_piengine.py | tail -1
python3 tests/run_sql_check.py | tail -1
node tests/test_engine.js | tail -1
python3 tests/test_app.py 2>&1 | grep -E "^(exceptions|interns)"
