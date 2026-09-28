#!/usr/bin/env bash
# Runs as the operator before the agent, with cwd = the run's sandbox cwd (only with --scaffold).
# Puts a synthetic Japanese-UI Search Console export in seo/data/ under the name Search Console gives
# it (<property>-Performance-on-Search-<export date>.zip). The zip is built by fixtures/build.py
# (7 CSVs at the top level, UTF-8 names with flags 0x0808, like a real export).
set -euo pipefail
mkdir -p seo/data
cp "$(dirname "$0")/fixtures/gsc-export-ja.zip" ./seo/data/example.jp-Performance-on-Search-2026-09-27.zip
test -s ./seo/data/example.jp-Performance-on-Search-2026-09-27.zip
