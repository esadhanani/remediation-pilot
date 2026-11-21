# Remediation pilot: bank open source

Stage one of a vulnerability-remediation programme (inventory, existing backlog, scoped fixes, scorecard), run on the public GitHub code of 23 banks and fintechs. Built to hand the scoped fixes to Devin.

## What it found (19 Nov 2026)

| | |
|---|---|
| Orgs / active public repos scanned | 23 / 491 |
| Repos with pinned dependencies in GitHub's dependency graph | 241 |
| Repos carrying a known high or critical advisory | 152 |
| High/critical matches (repo × package × advisory) | 5,297 |
| ...from advisories published in the last 90 days | 1,874 (35%) |
| Distinct upgrades that would close them | 1,932 |
| ...direct dependencies | 373 |
| ...direct, in repos that merged ≥5 human PRs in 180 days | 199 |
| Dependabot/Renovate PRs open across the orgs | 2,799 (median age 805 days; 1,652 older than a year) |
| Scoped upgrades that already have an open bot PR mentioning the package | 287 |
| Public Devin PRs in these 23 orgs / on all of GitHub | 0 / 350,891 |
| Tasks written for Devin / confirmed against the repo's own manifest | 25 / 22 |

Per-org and per-repo tables are written to `out/` and are not published here, because they name specific repositories. They are available on request.

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
- Bot-PR history is capped at 1,000 results per query by GitHub search, which truncates closed-PR history for FINOS, Morgan Stanley, Bloomberg and Adyen. Open-PR counts are complete.
- "Open bot PR mentioning the package" is a title match and can over-match similarly named packages.
- 3 of 25 tasks were not confirmed because the repos have more than 60 manifests and only the first 60 were read.
- The Devin stage has not been run yet.
