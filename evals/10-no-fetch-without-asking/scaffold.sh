#!/usr/bin/env bash
# Runs as the operator before the agent, with cwd = the run's sandbox cwd (only with --scaffold).
set -euo pipefail
cp "$(dirname "$0")/fixtures/queries-ja.csv" ./クエリ.csv
test -s ./クエリ.csv
