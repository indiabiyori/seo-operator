---
# Display-only report (arm: with-only): passes when references/00-principles.md was NOT read.
# A read of 00 already fails the scored no-unrelated-reference-reads guard (strict since
# 2026-09-27); this only shows whether 00 caused that failure. Keep it display-only, or the same
# read would be scored twice.
type: tool_used
tool: Read
input_match: 'references(?:/|\\\\)00-principles\.md'
min: 0
max: 0
arm: with-only
---
