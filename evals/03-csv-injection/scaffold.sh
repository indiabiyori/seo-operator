#!/usr/bin/env bash
# Runs as the operator before the agent, with cwd = the run's sandbox cwd.
# Only runs when `claude plugin eval` is given --scaffold. Without it there is no CSV in the
# workspace and every scored grader fails in both arms (score about 0, delta 0).
# The fixture is stored under an ASCII name so zip tools and Windows checkouts cannot mangle
# the file name; it is copied under the name the prompt uses (クエリ.csv, the file name in a
# Japanese-UI Search Console export). Format: UTF-8 without BOM, LF, the 5 columns of that
# export, rows sorted like the export (clicks descending, then impressions descending).
set -euo pipefail
cp "$(dirname "$0")/fixtures/queries-ja.csv" ./クエリ.csv
test -s ./クエリ.csv
