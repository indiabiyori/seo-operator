---
# Scored in both arms (weight 1). It passes trivially without the plugin, so it can only lower
# the with-arm score: a regression guard against over-reading, not a source of uplift.
# FAIL on any Read (full or partial) of a reference other than 07-on-page.md, or of templates/*
# or scripts/*. The routing table sends a title / meta description request to 07 only
# (併用: —), and the maintainer's rule for this case is 「必要な reference だけを読む」.
# 00-principles.md and 10-gsc-growth.md were tolerated in the first draft because SKILL.md's
# shared rules and 07 step 12 point to them; since 2026-09-27 they count as over-reads too
# (Codex review: otherwise the scored part never tests "only what is needed"). Their reads are
# still broken out by no-00-principles-read and no-10-gsc-read (display-only), so a failure
# here shows which pointer the skill followed.
# - scripts/*.py are the costliest over-read (57-141 KB).
# - The user's own seo/site-brief.md in the run cwd does not match (SKILL.md step 1 is fine).
# The separators accept "/" and the "\\" that JSON writes for a Windows path.
# Not covered: Grep (see no-unrelated-plugin-greps, display-only) and reads by a subagent.
type: tool_used
tool: Read
input_match: 'skills(?:/|\\\\)seo-operator(?:/|\\\\)(?:references(?:/|\\\\)(?!07-)[0-9]{2}-|templates(?:/|\\\\)|scripts(?:/|\\\\))'
min: 0
max: 0
arm: both
---
