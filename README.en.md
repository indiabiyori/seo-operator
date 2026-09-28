# seo-operator

[![test](https://github.com/indiabiyori/seo-operator/actions/workflows/test.yml/badge.svg)](https://github.com/indiabiyori/seo-operator/actions/workflows/test.yml)

日本語: [README.md](README.md)

An Agent Skill for doing SEO on Japanese-language websites with Claude Code. Its first rule is never to make up numbers: when search volume, rankings, or traffic data are missing, it tells you which tool and report to export them from instead of guessing. I built it for my own use and am publishing it as is.

Everything in the skill is written in Japanese: SKILL.md, the playbooks, the templates, and the scripts' help and messages. The drafts it produces (titles, meta descriptions, briefs, articles) are meant for Japanese sites. The full guide is the Japanese [README.md](README.md).

## What it does

- 12 playbooks that Claude reads per task: prioritization and spam-policy rules, site setup, technical audits, keyword research, topical maps, SERP analysis and content briefs, writing and rewriting, on-page elements, internal linking, AI search (AI Overviews, AI Mode, LLM citations), Search Console analysis, and link building.
- 4 Python scripts, none of which needs API credentials:
  - `audit.py` fetches the URLs listed in a sitemap (XML, gzip, plain-text URL lists, or RSS/Atom) and reports each page's status code, redirect target, title, meta description, h1 count, canonical URL, noindex, and text length.
  - `striking_distance.py` finds queries or pages at positions 8–20 with at least 100 impressions and estimates the extra clicks if their CTR reached your own top-3 CTR.
  - `low_ctr.py` finds rows in the top 10 with at least 100 impressions whose CTR is below half of your own CTR for the same position band.
  - `decay.py` compares two periods and flags rows that lost at least 30% of their clicks (and at least 10 clicks), with a likely cause.
- Ground rules written into SKILL.md:
  - Never invent metrics, first-hand experience, or case studies. Missing data is left as `[要追加: …]` ("to be added"), and estimates or points that need legal review are marked `[要確認: …]` ("to be confirmed").
  - Tie every action to a conversion and rank actions by impact ÷ effort.
  - Keep one URL per search intent.
  - Point out requests that may violate Google's spam policies and offer compliant alternatives.
  - Judge results by measured Search Console data, not predictions.

## Install

Windows has not been tested yet.

Claude Code (plugin), from a terminal:

```bash
claude plugin marketplace add indiabiyori/seo-operator
claude plugin install seo-operator@seo-operator
```

Or copy the folder by hand:

```bash
git clone https://github.com/indiabiyori/seo-operator.git
mkdir -p ~/.claude/skills
cp -R seo-operator/skills/seo-operator ~/.claude/skills/
```

On claude.ai (web or Cowork), zip the `skills/seo-operator` folder so that `seo-operator` is at the top of the zip, turn on "Code execution and file creation" in Settings → Capabilities, and upload the zip in Customize → Skills → "+" → "+ Create skill" → "Upload a skill".

When you use the skill in Cowork, connect a working folder for the site in the Claude desktop app before you ask. Claude can read and write files in a connected folder, so `seo/site-brief.md`, `seo/data/`, and `seo/output/` from the initial setup stay there. Without a connected folder, the files Claude creates stay in the conversation, and you download the ones you want to keep. Local folders are reachable only from tasks started in the desktop app, and only while the app is open; tasks started on the web or on a phone cannot reach them.

The scripts need Python 3.9 or later with requests, beautifulsoup4, and pandas. With [uv](https://docs.astral.sh/uv/), running a script with `uv run` installs them automatically from the metadata at the top of each script. When the packages are not on your machine yet, Claude asks before downloading them. Otherwise, create a virtual environment and run `pip install -r skills/seo-operator/requirements.txt` in it; Homebrew and many Linux system Pythons refuse a system-wide `pip install`. If a package is missing, the script prints how to install it.

To update a plugin install, run `claude plugin marketplace update seo-operator` and `claude plugin update seo-operator@seo-operator`, then restart Claude Code.

## Getting started

Create one working folder per site, open Claude Code there, and ask for the initial setup, for example `seo-operator で初回セットアップをして` ("run the seo-operator initial setup"). Claude creates `seo/site-brief.md` (business, conversions, audience, competitors, legal constraints) and `seo/voice-guide.md` (style and notation rules) from templates and fills them in with you. Unanswered items stay as `[要追加]`. Claude also creates `seo/data/` for the data you export and `seo/output/` for the scripts' results, and if the working folder is a Git repository, it asks whether to add both to `.gitignore`, since both hold per-query and per-page figures. Then put your data in `seo/data/` and ask for the analysis. A Search Console export can stay zipped: the scripts read the query or page table inside the zip without extracting it. The zip's file name holds the export date, not the date range, so when you export two periods, rename each zip to show its period.

## Using audit.py safely

Use `audit.py` only on your own sites or sites you have permission to crawl. By default it waits one second between requests and follows robots.txt. It never connects to private or internal IP addresses (redirects included) and skips sitemap entries on hosts other than the sitemap's own; redirects to other public hosts are followed. If robots.txt cannot be fetched because of a server error or a network error (as RFC 9309 requires), or it returns 429 (as Google treats it), the script skips every URL that robots.txt covers and marks it `BLOCKED:robots-unreachable`. On your own site, add `--ignore-robots` to continue.

## Tests

All 249 regression tests passed on macOS with Python 3.9 + pandas 2.3 and Python 3.13 + pandas 3.0 (2026-09-28). GitHub Actions runs the same tests on Ubuntu with Python 3.9 and 3.13 on every push to main and every pull request, and also on Python 3.9 with each dependency at the lowest version that requirements.txt allows. See [tests/README.md](tests/README.md) (in Japanese) for how to run them.

The behavior evals in [evals/](evals/README.md) (in Japanese) measure how Claude answers. There are twelve scenarios, each run three times with the skill and three times without it (six times each for the proofreading scenario), and each run is scored from 0 to 1. They check, for example, that Claude does not invent search volumes, that it flags spam-policy risk when asked to mass-produce landing pages that differ only in the prefecture name, that it ignores instructions hidden in a CSV, that the skill stays out of proofreading that has nothing to do with SEO, that it does not create files or download packages nobody asked for, and that in a Git repository it asks before adding the data folders to `.gitignore`. In the 2026-09-27 run of version 1.2.0, Claude with the skill scored full marks in all ten scenarios that existed then. Five of them check that the skill does not make things worse, and also scored full marks without it. The largest gains were on the search-volume request (1.00 with the skill, 0.29 without) and on the request to run the first-time setup (1.00 and 0.33). The scenario that asks for at most three kinds of data scored 0.70 in version 1.1.0 and 1.00 in version 1.2.0. For version 1.3.0, the nine scenarios that the change can affect were run before and after the change, and Claude with the skill scored full marks in all nine. The new `.gitignore` scenario went from 0.67 with version 1.2.0 (which never asked about `.gitignore`) to 1.00. For version 1.4.0, the three scenarios that handle Search Console data were run before and after the change, and Claude with the skill scored full marks in all three. Each scenario ran only three times, so only large differences are meaningful.

## Limitations

- It cannot provide actual search volumes or keyword difficulty. Give it an Ahrefs or Semrush export, or use Google Trends for relative comparisons.
- It assumes a Japanese-language site. Character-count targets for titles and descriptions, notation variants, and legal checks (such as Japan's rules on stealth marketing) follow Japanese conventions and law.
- The ground rules are only instructions in SKILL.md, so Claude does not always follow them. The evals made the rough search-volume request six times with the skill and six times without, across two full runs. With the skill, one answer gave numbers: while explaining why it would not estimate, it attached example figures to the keywords (first run; none of the three answers in the second run did). Without the skill, all six answers gave numbers. Ask where a number came from if its source is unclear.

## License and attribution

MIT (see [LICENSE](LICENSE)). Parts of the playbooks in `skills/seo-operator/references/` summarize and adapt [Google Search Central documentation](https://developers.google.com/search/docs), which Google publishes under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), with code samples under [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for third-party works and licenses.

Version 1.4.0 (last updated 2026-09-27).
