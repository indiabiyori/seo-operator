---
# Display-only (arm: with-only): the routing table in SKILL.md sends title / meta description
# requests to references/07-on-page.md. Not scored, because the without arm has no plugin file
# to read and a scored check would inflate the delta. Partial reads (offset/limit) also count.
# The separators accept "/" and the "\\" that JSON writes for a Windows path.
type: tool_used
tool: Read
input_match: 'references(?:/|\\\\)07-on-page\.md'
min: 1
arm: with-only
---
