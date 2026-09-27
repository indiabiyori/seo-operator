---
# The runner lists files created during the run. Writing seo/site-brief.md, seo/voice-guide.md or any
# other file under seo/ without being asked is the v1.2.0 behaviour this case guards against.
type: file_exists
path: seo/**
exists: false
weight: 2
arm: both
---
