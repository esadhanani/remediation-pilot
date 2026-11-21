#!/usr/bin/env python3
"""Step 2: enrich, measure the existing backlog, and scope the pilot.

Reads data/findings.jsonl + data/repos.jsonl (from inventory.py) and writes:
  data/vulns.json        OSV advisory details (severity, fixed versions), cached
  data/bot_prs.jsonl     every Dependabot/Renovate PR in the orgs (open + closed)
  out/org_summary.csv    one row per org: exposure and how fast fixes get merged
  out/pilot_scope.csv    ranked fix candidates (the pilot backlog)
  out/tasks/*.md         one ready-to-run agent task per top candidate
"""
import collections
import concurrent.futures as cf
import csv
import datetime as dt
import json
import pathlib
import re
import statistics
import sys
import time

from inventory import DATA, HERE, ORGS, gh, http

OUT = HERE / "out"
NOW = dt.datetime.now(dt.timezone.utc)
SEV_RANK = {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
BOTS = ["app/dependabot", "app/renovate"]


def load_jsonl(p):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def vkey(v):
    """Sortable version key good enough for picking the lowest fixed version above current."""
    return [int(x) if x.isdigit() else x for x in re.split(r"[.\-+_]", v.lstrip("v")) if x != ""]


def cmp_ok(a, b):
    try:
        return vkey(a) < vkey(b)
    except TypeError:
        return None


def fetch_vulns(ids):
    cache_p = DATA / "vulns.json"
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    todo = [i for i in ids if i not in cache]

    def one(i):
        return i, http("https://api.osv.dev/v1/vulns/" + i)

    with cf.ThreadPoolExecutor(12) as ex:
        for n, (i, d) in enumerate(ex.map(one, todo), 1):
            if d:
                cache[i] = {
                    "id": i, "aliases": d.get("aliases", []), "summary": d.get("summary", ""),
                    "severity": (d.get("database_specific", {}).get("severity") or "UNKNOWN").upper(),
                    "published": d.get("published", ""), "withdrawn": d.get("withdrawn"),
                    "affected": [{"eco": a.get("package", {}).get("ecosystem"),
                                  "name": a.get("package", {}).get("name"),
                                  "fixed": [e["fixed"] for r in a.get("ranges", []) for e in r.get("events", [])
                                            if "fixed" in e]} for a in d.get("affected", [])],
                }
            if n % 200 == 0:
                print(f"advisories fetched {n}/{len(todo)}", flush=True)
    cache_p.write_text(json.dumps(cache))
    return cache


def fixed_version(v, eco, name, current):
    """Lowest published fix above the current version, for this package."""
    cands = [f for a in v["affected"] if a["eco"] == eco and (a["name"] or "").lower() == name.lower()
             for f in a["fixed"]]
    above = [f for f in cands if cmp_ok(current, f)]
    if not above:
        return ""
    try:
        return sorted(above, key=vkey)[0]
    except TypeError:
        return above[0]


def search_prs(q):
    """GitHub search, all pages (max 1000 results per query)."""
    out, page = [], 1
    while page <= 10:
        d = gh(f"/search/issues?q={q}&sort=created&order=desc&per_page=100&page={page}")
        time.sleep(2.2)  # search API allows 30 requests a minute
        if not d or not d.get("items"):
            break
        out += d["items"]
        if len(d["items"]) < 100:
            break
        page += 1
    return out


def fetch_bot_prs():
    p = DATA / "bot_prs.jsonl"
    if p.exists():
        return load_jsonl(p)
    since = (NOW - dt.timedelta(days=365)).strftime("%Y-%m-%d")
    rows = []
    for o in ORGS:
        for bot in BOTS:
            for state in ("is:open", f"is:closed+closed:>{since}"):
                items = search_prs(f"is:pr+org:{o['org']}+author:{bot}+{state}")
                for it in items:
                    rows.append({"org": o["org"], "repo": it["repository_url"].split("/repos/")[1],
                                 "bot": bot.split("/")[1], "number": it["number"], "title": it["title"],
                                 "state": it["state"], "created": it["created_at"], "closed": it["closed_at"],
                                 "merged": bool(it.get("pull_request", {}).get("merged_at")),
                                 "security": any("security" in l["name"].lower() for l in it.get("labels", []))})
        print(f"{o['org']:18} bot PRs so far: {len(rows)}", flush=True)
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return rows


def repo_activity(repo_list):
    """Human (non-bot) PRs merged in the last 180 days, per repo, from the 100 most recently
    updated closed PRs (so the count tops out at 100). Cached."""
    p = DATA / "repo_activity.json"
    cache = json.loads(p.read_text()) if p.exists() else {}
    since = (NOW - dt.timedelta(days=180)).isoformat()
    for i, repo in enumerate([r for r in repo_list if r not in cache], 1):
        d = gh(f"/repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=100")
        time.sleep(0.4)
        if d is not None:
            cache[repo] = sum(1 for x in d if x.get("merged_at") and x["merged_at"] > since
                              and x["user"]["type"] != "Bot")
        if i % 20 == 0:
            print(f"repo activity {i}", flush=True)
            p.write_text(json.dumps(cache))
    p.write_text(json.dumps(cache))
    return cache


def days(a, b=None):
    t0 = dt.datetime.fromisoformat(a.replace("Z", "+00:00"))
    t1 = dt.datetime.fromisoformat(b.replace("Z", "+00:00")) if b else NOW
    return (t1 - t0).total_seconds() / 86400


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "tasks").mkdir(exist_ok=True)
    repos = {r["repo"]: r for r in load_jsonl(DATA / "repos.jsonl")}
    raw = load_jsonl(DATA / "findings.jsonl")
    vul = fetch_vulns(sorted({r["vuln"] for r in raw}))

    # --- findings: keep GitHub-reviewed advisories with a severity, drop withdrawn
    finds = []
    for r in raw:
        v = vul.get(r["vuln"])
        if not v or v["withdrawn"] or not r["vuln"].startswith("GHSA-"):
            continue
        fx = fixed_version(v, r["ecosystem"], r["package"], r["version"])
        cve = next((a for a in v["aliases"] if a.startswith("CVE-")), "")
        finds.append({**r, "severity": v["severity"], "fixed": fx, "cve": cve, "summary": v["summary"],
                      "published": v["published"][:10],
                      "age_days": round(days(v["published"])) if v["published"] else None})

    # --- existing remediation backlog per repo and org (Dependabot / Renovate)
    bots = fetch_bot_prs()
    by_repo = collections.defaultdict(list)
    for b in bots:
        by_repo[b["repo"]].append(b)

    def bot_stats(prs):
        op = [b for b in prs if b["state"] == "open"]
        cl = [b for b in prs if b["state"] == "closed"]
        mg = [b for b in cl if b["merged"]]
        return {"open": len(op), "open_median_age": round(statistics.median(days(b["created"]) for b in op)) if op else "",
                "closed_12m": len(cl), "merged_12m": len(mg),
                "merge_rate": round(len(mg) / len(cl), 2) if cl else "",
                "median_days_to_merge": round(statistics.median(days(b["created"], b["closed"]) for b in mg), 1) if mg else ""}

    # --- org summary
    org_rows = []
    for o in ORGS:
        rs = [r for r in repos.values() if r["org"] == o["org"]]
        fs = [f for f in finds if f["org"] == o["org"]]
        hi = [f for f in fs if SEV_RANK[f["severity"]] >= 3]
        fixable = [f for f in hi if f["fixed"]]
        st = bot_stats([b for b in bots if b["org"] == o["org"]])
        org_rows.append({"org": o["org"], "name": o["name"], "cognition_named_customer": o["named_customer"],
                         "active_repos": len(rs), "repos_with_sbom": sum(r["sbom"] and r["packages"] > 0 for r in rs),
                         "repos_with_high_or_critical": len({f["repo"] for f in hi}),
                         "critical": sum(f["severity"] == "CRITICAL" for f in fs),
                         "high": sum(f["severity"] == "HIGH" for f in fs),
                         "high_critical_with_fix": len(fixable),
                         "median_age_days_high_critical": round(statistics.median(f["age_days"] for f in hi)) if hi else "",
                         "bot_prs_open": st["open"], "bot_prs_open_median_age_days": st["open_median_age"],
                         "bot_prs_closed_12m": st["closed_12m"], "bot_merge_rate_12m": st["merge_rate"],
                         "bot_median_days_to_merge": st["median_days_to_merge"]})
    with open(OUT / "org_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(org_rows[0]))
        w.writeheader()
        w.writerows(org_rows)

    # --- pilot scope: one candidate per repo x package (one bump closes all its high/critical advisories)
    grp = collections.defaultdict(list)
    for f in finds:
        if SEV_RANK[f["severity"]] >= 3 and f["fixed"]:
            grp[(f["repo"], f["ecosystem"], f["package"])].append(f)
    act = repo_activity(sorted({k[0] for k, fs in grp.items() if any(f["direct"] for f in fs)}))
    cands = []
    for (repo, eco, pkg), fs in grp.items():
        versions = sorted({f["version"] for f in fs}, key=lambda v: str(vkey(v)))
        ver = versions[0]
        try:
            target = sorted({f["fixed"] for f in fs}, key=vkey)[-1]
        except TypeError:
            target = fs[0]["fixed"]
        ids = sorted({f["cve"] or f["vuln"] for f in fs})
        st = bot_stats(by_repo.get(repo, []))
        r = repos[repo]
        sev = max(SEV_RANK[f["severity"]] for f in fs)
        same_major = all(vkey(v)[:1] == vkey(target)[:1] for v in versions)
        direct = any(f["direct"] for f in fs)
        short = pkg.split(":")[-1].split("/")[-1].lower()
        stuck = [b for b in by_repo.get(repo, []) if b["state"] == "open" and short in b["title"].lower()]
        human = act.get(repo)
        score = (sev * 10 + min(len(ids), 10) * 2 + (10 if direct else 0) + (5 if same_major else 0)
                 + (8 if stuck else 0) + min(r["stars"], 5000) / 500
                 + (0 if human is None else 15 if human >= 20 else 10 if human >= 5 else 3 if human >= 1 else -30))
        cands.append({"score": round(score, 1), "repo": repo, "stars": r["stars"], "ecosystem": eco, "package": pkg,
                      "current": " / ".join(versions), "fix_version": target, "direct_dependency": direct,
                      "same_major_bump": same_major,
                      "max_severity": {4: "CRITICAL", 3: "HIGH"}[sev], "advisories_closed": len(ids),
                      "advisory_ids": " ".join(ids),
                      "newest_advisory": max(f["published"] for f in fs),
                      "oldest_advisory_days": max(f["age_days"] or 0 for f in fs),
                      "open_bot_pr_for_package": f"#{stuck[0]['number']} open {round(days(stuck[0]['created']))}d" if stuck else "",
                      "human_prs_merged_180d": "" if human is None else human,
                      "repo_bot_prs_merged_12m": st["merged_12m"], "repo_bot_median_days_to_merge": st["median_days_to_merge"],
                      "repo_last_push": r["pushed_at"][:10]})
    cands.sort(key=lambda c: -c["score"])
    with open(OUT / "pilot_scope.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cands[0]))
        w.writeheader()
        w.writerows(cands)

    # --- tasks: direct dependencies, in repos whose maintainers merged >=5 human PRs in 180 days, max 2 per repo
    per_repo, n = collections.Counter(), 0
    for old in (OUT / "tasks").glob("*.md"):
        old.unlink()
    for c in cands:
        if n >= 25:
            break
        if not c["direct_dependency"] or per_repo[c["repo"]] >= 2 or (c["human_prs_merged_180d"] or 0) < 5:
            continue
        per_repo[c["repo"]] += 1
        n += 1
        fs = {f["vuln"]: f for f in grp[(c["repo"], c["ecosystem"], c["package"])]}.values()
        adv = "\n".join(f"- {f['cve'] or f['vuln']} ({f['severity']}, published {f['published']}): {f['summary']}"
                        for f in sorted(fs, key=lambda f: (-SEV_RANK[f["severity"]], f["published"])))
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", f"{c['repo']}-{c['package']}").strip("-").lower()
        first = next(iter(sorted(fs, key=lambda f: -SEV_RANK[f["severity"]])))
        (OUT / "tasks" / f"{n:02d}-{slug}.md").write_text(f"""# {c['repo']}: upgrade {c['package']} {c['current']} -> {c['fix_version']}

Repository: https://github.com/{c['repo']}
Ecosystem: {c['ecosystem']} | direct dependency | {'same-major' if c['same_major_bump'] else 'MAJOR'} bump
Maintainers merged {c['human_prs_merged_180d']} human PRs in the last 180 days.
Existing bot PR for this package: {c['open_bot_pr_for_package'] or 'none'}

## Advisories this closes ({c['advisories_closed']})
{adv}

## Task
1. Find every manifest and lockfile that pins `{c['package']}` at `{c['current']}` and raise it to `{c['fix_version']}` (or the lowest later version that still builds).
2. Regenerate lockfiles with the project's own package manager. Do not hand-edit them.
3. Read the upstream changelog between the two versions. If an API the repo uses changed, fix the call sites.
4. Run the project's build and full test suite exactly as CONTRIBUTING / CI does. Paste the commands and the pass/fail summary in the PR body.
5. Open one PR containing only this change. Title: `Bump {c['package'].split(':')[-1]} to {c['fix_version']} ({first['cve'] or first['vuln']})`. In the body list the advisories above, state whether the vulnerable code path is reachable from this repo, and follow the repo's contribution rules (CLA / DCO sign-off).
6. If the bump cannot be made to pass, stop and report exactly which test fails and why. Do not open the PR.
""")

    # --- headline numbers
    hi = [f for f in finds if SEV_RANK[f["severity"]] >= 3]
    uniq = {(f["repo"], f["package"], f["vuln"]) for f in hi}
    recent = {k for k, f in ((( f["repo"], f["package"], f["vuln"]), f) for f in hi) if (f["age_days"] or 9999) <= 90}
    op = [b for b in bots if b["state"] == "open"]
    summary = {
        "generated": NOW.strftime("%Y-%m-%d"), "orgs": len(ORGS), "active_repos": len(repos),
        "repos_with_pinned_dependencies": sum(r["sbom"] and r["packages"] > 0 for r in repos.values()),
        "repos_with_high_or_critical": len({f["repo"] for f in hi}),
        "high_critical_matches_repo_package_advisory": len(uniq),
        "of_which_advisory_published_last_90d": len(recent),
        "distinct_high_critical_advisories": len({f["vuln"] for f in hi}),
        "fix_candidates_repo_x_package": len(cands),
        "fix_candidates_direct": sum(c["direct_dependency"] for c in cands),
        "fix_candidates_direct_in_repos_that_merge": sum(1 for c in cands if c["direct_dependency"] and (c["human_prs_merged_180d"] or 0) >= 5),
        "open_bot_prs": len(op), "open_bot_prs_older_than_1y": sum(days(b["created"]) > 365 for b in op),
        "open_bot_pr_median_age_days": round(statistics.median(days(b["created"]) for b in op)),
        "tasks_written": n,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    print(f"findings kept: {len(finds)} | high/critical: {sum(SEV_RANK[f['severity']] >= 3 for f in finds)} "
          f"| fix candidates: {len(cands)} | tasks written: {n} | bot PRs: {len(bots)}")


if __name__ == "__main__":
    sys.exit(main())
