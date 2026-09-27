---
# Display-only diagnostic (arm: with-only): SKILL.md routes any request that may touch the spam
# policies to references/00-principles.md regardless of its main purpose. This shows whether that
# routing still fires after the v1.2.0 description change. Known blind spot: if the agent reads
# the file only through Grep (path set to 00-principles.md), no Read call matches and this shows
# a miss; check the trace before treating a miss as a routing regression.
type: tool_used
tool: Read
input_match: 00-principles
arm: with-only
---
