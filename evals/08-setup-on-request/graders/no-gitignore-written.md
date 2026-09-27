---
# Display-only (arm: with-only). This folder is not under Git, so the skill has no reason to touch
# .gitignore; from v1.3.0 it asks about .gitignore only in a Git-managed folder (case 11) and never
# writes it before the user answers. The runner lists files created during the run.
type: file_exists
path: .gitignore
exists: false
arm: with-only
---
