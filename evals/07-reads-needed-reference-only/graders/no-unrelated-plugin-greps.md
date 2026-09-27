---
# Display-only (arm: with-only): the scored read guard only sees Read. This reports any Grep whose
# path is inside the plugin's skill directory, except a Grep aimed at SKILL.md or 07-on-page.md:
# a sweep of the skill root, references/, templates/ or scripts/, or a Grep of an unrelated file.
# Not scored, because a files_with_matches Grep over a directory only lists file names, and the
# regex cannot separate it from a content-mode Grep without depending on key order. If the pilot
# shows content-mode greps here, promote it to arm: both.
type: tool_used
tool: Grep
input_match: '"path"\s*:\s*"[^"]*skills(?:/|\\\\)seo-operator(?!(?:/|\\\\)(?:references(?:/|\\\\)07-[^"/\\]*|SKILL\.md)")'
min: 0
max: 0
arm: with-only
---
