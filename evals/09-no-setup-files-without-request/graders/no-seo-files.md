---
# The runner lists files created during the run (files only; an empty mkdir is not listed). Writing
# any file under seo/ fails here: seo/site-brief.md or seo/voice-guide.md without being asked, a copy
# of templates/30-day-plan.md (the plan belongs in the reply), or anything under seo/data/ or
# seo/output/. From v1.3.0 SKILL.md lets script output go to seo/output/ outside the setup, but this
# request gives no data and no URL, so no script has anything to write. Kept as seo/** so that the
# v1.2.0 and v1.3.0 runs are graded the same way.
type: file_exists
path: seo/**
exists: false
weight: 2
arm: both
---
