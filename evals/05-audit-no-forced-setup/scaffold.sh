#!/usr/bin/env bash
# Runs as the operator before the agent, with cwd = the run's sandbox cwd.
# Only runs when `claude plugin eval` is given --scaffold; without it the
# workspace is empty and this case cannot pass in either arm.
# Puts the crawl export the prompt refers to ("このフォルダの audit.csv") into cwd.
# The fixture mirrors the output format of the plugin's crawl script:
# UTF-8 with BOM, CRLF, 12 columns in the script's order.
set -euo pipefail
cp "$(dirname "$0")/fixtures/audit.csv" ./audit.csv
