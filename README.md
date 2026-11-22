# Which dependency upgrades need an engineer?

I built this pilot to decide which stalled dependency upgrades to hand to Devin. I inventoried 491 public financial-sector repositories, scoped 25 upgrades and investigated three with Devin.

Two findings changed how I would run a customer pilot.

- **Establish what happens without intervention.** Among 335 historical bot PRs still open at day 30, only 19 merged over the following month. Another 46 closed unmerged and 270 stayed open.
- **Check the build environment before assigning the upgrade.** Across two FINOS projects, 31 PRs encountered failures after the same runner-image change. In a third project the upgrade broke a package import. A two-line patch restored the 127-module build on Devin's machine.

The [one-line workflow patch](evidence/control-center.patch) and [two-line source patch](evidence/bpm-platform.patch) show the difference. The tables below give the comparison cohort, the checks run and the remaining verification work.

## Try the pilot offline

```sh
python3 pilot_review.py
python3 pilot_review.py --day 7 --window 14
```

The first command replays observed outcomes and three recorded investigations using Python 3.9+ and its standard library. The second lets you change the age and follow-up window. Neither command accesses a network or launches Devin.

### What happened to upgrades left open?

A cohort of 1,069 dependency-bot pull requests across 73 repositories had at least 120 days of observable history. At each age below, the denominator contains only PRs still open at that point.

| Age at decision | Still eligible | Merged in next 30 days | Closed unmerged | Still open 30 days later |
|---|---:|---:|---:|---:|
| On opening | 1,069 | 328 (30.7%) | 406 | 335 |
| 30 days | 335 | 19 (5.7%) | 46 | 270 |
| 90 days | 240 | 11 (4.6%) | 15 | 214 |

That gives a team a baseline for a pilot: of the 335 upgrades still open after a month, 270 were still open a month later. A future trial could assign eligible upgrades to assisted and usual handling within each repository and compare merge, unmerged closure and engineer time over the same window. The historical comparisons alone cannot estimate the effect of Devin or waiting.

**Method.** The 19 November 2026 snapshot includes open PRs and one year of closed PR history. We selected PRs opened from 20 November 2025 through 21 July 2026 inclusive (UTC). We excluded entire organisations where any bot/state query reached GitHub's 1,000-result cap. Fifteen organisations contributed eligible PRs. We count merge and unmerged closure separately, using final observed closure timestamps. The snapshot cannot reconstruct temporary closes or reopenings. Bot PRs include routine updates. Repository mix and review policies can influence these rates.

[Anonymous daily counts](evidence/cohort.csv) · [Cohort construction](cohort.py). To rebuild the counts from the original private snapshot, run `python3 cohort.py data/bot_prs.jsonl`. The published counts are enough to recalculate every table cell.

### Which intervention fits the evidence?

| Investigation | What an engineer can check | Proposed change |
|---|---|---|
| Fluxnova control center | Base and upgrade showed the same browser-install failure on the newer image. Both passed the end-to-end suite on the older image in containers. Verify the runner pin in hosted CI. | [One-line workflow diff](evidence/control-center.patch) |
| PyLegend | The Python setup failure recurred across 12 upgrades. A local test pass with Python already installed leaves hosted setup untested. | [Matrix diff](evidence/pylegend.patch) |
| Fluxnova BPM platform | Retaining the dependency upgrade and changing the import restored the 127-module build. | [Two-line source diff](evidence/bpm-platform.patch) |

[Case records and upstream links](evidence/cases.json) include the checks, environments and missing controls. The replay reads manually transcribed run summaries. It does not re-execute the upstream suites or infer a failure cause from raw logs. To check the cohort boundaries and decision rules, run `python3 -m unittest discover -s tests -v`.

## Inventory (19 Nov 2026)

| | |
|---|---|
| Orgs / active public repos scanned | 23 / 491 |
| Repos with pinned dependencies in GitHub's dependency graph | 241 |
| Repos with pinned versions matching a high or critical advisory | 152 |
| High/critical matches (repo × package × advisory) | 5,297 |
| ...from advisories published in the last 90 days | 1,874 (35%) |
| Candidate repository/package upgrades | 1,932 |
| ...direct dependencies | 373 |
| ...direct, in repos that merged ≥5 human PRs in 180 days | 199 |
| Dependabot/Renovate PRs open across the orgs | 2,799 (median age 805 days; 1,652 older than a year) |
| Scoped upgrades that already have an open bot PR mentioning the package | 287 |
| Tasks written for Devin / confirmed against the repo's own manifest | 25 / 22 |

The published cohort contains daily aggregate counts. The inventory workflow stores per-repository results locally.

## First fixes run through Devin (21 Nov 2026)

Three selected tasks were handed to Devin Cloud. Each had a bot security upgrade that had been failing CI. Devin was told to reproduce the failure with the repo's own CI commands, fix it, and re-run the tests. The case records distinguish the original CI failures from local reruns.

| Repo | Blocked | Root cause | Fix | Tests after |
|---|---|---|---|---|
| finos/pylegend | all 12 open Renovate security PRs | `ubuntu-latest` became Ubuntu 26.04, which has no Python 3.9 build for `setup-python` | 7 lines of workflow config | 1,770 passed on Python 3.9 |
| finos/fluxnova-control-center | `develop` and 19 of 22 open PRs | same runner change; Playwright 1.58.2 cannot install Chromium on 26.04 | 1 line of workflow config | 187 end-to-end passed |
| finos/fluxnova-bpm-platform | fast-xml-parser v5 security upgrade | code imports an internal path that v5's `exports` map hides | 2 lines of code | 26,032 unit tests reported (118 skipped, zero failures or errors); 220 integration tests reported with zero failures |

Two projects exhibited setup failures after the runner image changed. The public cases are selected examples. The reported reruns used Devin environments. Each case has a proposed patch, with upstream verification pending in the pilot snapshot.

## Run it

```bash
python3 inventory.py   # SBOM for every active repo -> OSV.dev matches        (~10 min)
python3 scope.py       # advisory details, bot-PR backlog, ranked scope, tasks (~15 min first run)
python3 verify.py      # checks each task against the repo's real manifests
./run_devin.sh out/tasks/01-*.md   # hands one task to a Devin Cloud session
python3 scorecard.py   # merge rate and time-to-merge for PRs listed in pilot_prs.txt
```

Needs Python 3.9+, the `gh` CLI signed in (read-only API calls), and for step four the Devin CLI on a Pro plan. Edit `orgs.json` to point it at any other set of orgs.

## Outputs

- `out/org_summary.csv`: exposure and bot-PR merge behaviour per org.
- `out/pilot_scope.csv`: every candidate upgrade, ranked. Score favours severity, direct dependencies, same-major bumps, repos that merge human PRs, and packages where a bot PR is already stuck.
- `out/tasks/NN-*.md`: one self-contained task per upgrade (advisories, steps, PR rules, stop condition).
- `out/verification.csv`: file and line where each task's vulnerable pin was found.

## Limits

- A match means the pinned version is in an advisory's affected range. Reachability is not assessed. Dev and transitive dependencies are included in the totals; tasks use direct dependencies only.
- Only repos pushed in the last 365 days, non-fork, non-archived. Repos without a lockfile or pinned manifest have no SBOM packages and are not assessed.
- Advisories are GitHub-reviewed (GHSA) records served by OSV.dev; withdrawn ones are dropped.
- Bot-PR history is capped at 1,000 results per query by GitHub search, which truncates closed-PR history for FINOS, Morgan Stanley, Bloomberg and Adyen. No open-PR query reached the cap in this snapshot.
- "Open bot PR mentioning the package" is a title match and can over-match similarly named packages.
- 3 of 25 tasks were not confirmed because the repos have more than 60 manifests and only the first 60 were read.
- Only three of the 25 scoped tasks have been run through Devin so far, and none of the fixes has been merged upstream yet.
