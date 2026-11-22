# Which dependency upgrades need an engineer?

I looked at 491 public financial-sector repositories, scoped 25 dependency upgrades and investigated three with Devin. In one case, a browser test was failing on an upgrade. The original branch failed at the same step. Both branches passed 187 end-to-end tests on the older Ubuntu image in containers. The change I would send to the maintainer is [one line in the workflow](evidence/control-center.patch).

### Which intervention fits the evidence?

| Project | What failed | What I could verify |
|---|---|---|
| Fluxnova control center | The browser installer stopped on the new runner image. The base branch and 19 of 22 open PRs hit the failure. | The base branch and one upgrade passed on Ubuntu 24.04 in containers. The proposed pin still needs a hosted run. [Workflow diff](evidence/control-center.patch) |
| PyLegend | All 12 open security-upgrade PRs stopped while setting up Python 3.9 after the same image change. | With Python 3.9 available locally, 1,770 tests passed and 33 skipped. The last successful base run predated the image change. [Matrix diff](evidence/pylegend.patch) |
| Fluxnova BPM platform | An upgraded package stopped exposing the internal import used by the application. | Switching to the public API restored the 127-module build on Devin's machine. The unit run reported 26,032 tests, zero failures or errors and 118 skipped. [Two-line source diff](evidence/bpm-platform.patch) |

These were three selected cases. The patches were local at the time of the pilot. The [case notes](evidence/cases.json) link to the original PRs and record the checks and environments.

## How often do stalled upgrades merge?

Of 335 bot PRs still open a month after creation, 19 merged over the next month. Another 46 closed unmerged and 270 stayed open.

| Age at decision | Still eligible | Merged in next 30 days | Closed unmerged | Still open 30 days later |
|---|---:|---:|---:|---:|
| On opening | 1,069 | 328 (30.7%) | 406 | 335 |
| 30 days | 335 | 19 (5.7%) | 46 | 270 |
| 90 days | 240 | 11 (4.6%) | 15 | 214 |

The cohort includes 1,069 Dependabot and Renovate PRs across 73 repositories in 15 organisations. I used the 19 November 2026 snapshot and selected PRs opened from 20 November 2025 through 21 July 2026 (UTC), allowing 120 days of follow-up. I excluded organisations where a bot query reached GitHub's 1,000-result cap. Each row includes only PRs open at that age, using the last recorded closure date. Temporary closures and reopenings cannot be reconstructed from this snapshot.

This gives a baseline for a future pilot. To measure Devin's contribution, I would assign comparable open upgrades within each repository to assisted or usual handling and track merges, closures and engineer time.

### Recalculate the table

```sh
python3 pilot_review.py
python3 pilot_review.py --day 7 --window 14
python3 -m unittest discover -s tests -v
```

Python 3.9+ is sufficient. The script calculates outcomes from the [daily counts](evidence/cohort.csv) and displays the saved case notes. The second command changes the age and follow-up window. [Cohort construction](cohort.py) shows how the private snapshot was reduced to daily counts.

## Inventory coverage

On 19 November, 241 of the 491 repositories had pinned dependencies I could assess. In 152 I found at least one pinned version matching a high or critical advisory. This includes development and transitive dependencies. Runtime reachability was outside the scope of the pilot. The original snapshot did not record failed advisory batches separately, so its coverage cannot be fully reconstructed. The current collector stops before writing its snapshot if a batch lookup fails or returns a partial result.

Across the 23 organisations, 2,799 automated upgrade PRs were open, with a median age of 805 days. I scoped 25 tasks and confirmed 22 against the repositories' manifests. The verifier's 60-file limit left three unconfirmed.

## Rebuild the inventory

```bash
python3 inventory.py   # SBOM for every active repo -> OSV.dev matches        (~10 min)
python3 scope.py       # advisory details, bot-PR backlog, ranked scope, tasks (~15 min first run)
python3 verify.py      # checks each task against the repo's real manifests
./run_devin.sh out/tasks/01-*.md   # hands one task to a Devin Cloud session
python3 scorecard.py   # merge rate and time-to-merge for PRs listed in pilot_prs.txt
```

Needs Python 3.9+, the `gh` CLI signed in (read-only API calls), and for step four the Devin CLI on a Pro plan. Edit `orgs.json` to point it at any other set of orgs.
