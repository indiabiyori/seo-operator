#!/usr/bin/env bash
# Runs as the operator before the agent, with cwd = the run's sandbox cwd (only with --scaffold).
# Makes the working folder a Git repository, as the prompt says. The agent's Bash runs in a
# sandbox where git itself does not work on macOS (xcode-select cannot write its cache), so the
# agent can only see the .git folder; git init runs here, outside the sandbox.
# No .gitignore is created: the runner lists only files created during the run, so a
# .gitignore written by the agent is detectable only when none exists beforehand.
set -euo pipefail
git init -q .
test -d .git
test ! -e .gitignore
