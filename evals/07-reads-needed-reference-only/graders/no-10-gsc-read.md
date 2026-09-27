---
# Display-only report (arm: with-only): passes when references/10-gsc-growth.md was NOT read.
# A read of 10 already fails the scored no-unrelated-reference-reads guard (strict since
# 2026-09-27); this only shows whether 10 caused that failure. SKILL.md's output rules and 07 step
# 12 both point to 10 for measurement timing, although 07 step 12 already states the window.
# Keep it display-only, or the same read would be scored twice.
type: tool_used
tool: Read
input_match: 'references(?:/|\\\\)10-gsc-growth\.md'
min: 0
max: 0
arm: with-only
---
