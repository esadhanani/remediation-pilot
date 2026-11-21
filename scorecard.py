#!/usr/bin/env python3
"""Step 4: pilot scorecard. Reads pilot_prs.txt (one GitHub PR URL per line) and
reports PR velocity, merge rate and time to merge, the three numbers the
remediation programme tracks. Works on any list of PR URLs."""
import csv
import re
import statistics
import sys

from inventory import HERE, gh
from scope import days

def main(path=HERE / "pilot_prs.txt"):
    rows = []
    for line in open(path):
        m = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", line)
        if not m:
            continue
        pr = gh(f"/repos/{m[1]}/pulls/{m[2]}")
        if not pr:
            continue
        checks = gh(f"/repos/{m[1]}/commits/{pr['head']['sha']}/check-runs") or {}
        concl = [c["conclusion"] for c in checks.get("check_runs", []) if c["conclusion"]]
        rows.append({"pr": f"{m[1]}#{m[2]}", "title": pr["title"][:70], "author": pr["user"]["login"],
                     "state": "merged" if pr["merged_at"] else pr["state"],
                     "opened": pr["created_at"][:10],
                     "days_open_or_to_merge": round(days(pr["created_at"], pr["merged_at"] or pr["closed_at"]), 1),
                     "ci": "pass" if concl and all(c in ("success", "neutral", "skipped") for c in concl)
                           else "fail" if concl else "none",
                     "review_comments": pr["review_comments"], "files": pr["changed_files"]})
    if not rows:
        print("no PRs in", path)
        return
    w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    merged = [r for r in rows if r["state"] == "merged"]
    closed = [r for r in rows if r["state"] == "closed"]
    print(f"\nopened {len(rows)} | merged {len(merged)} | closed unmerged {len(closed)} | still open {len(rows)-len(merged)-len(closed)}")
    if merged or closed:
        print(f"merge rate of decided PRs: {len(merged)/(len(merged)+len(closed)):.0%}")
    if merged:
        print(f"median days to merge: {statistics.median(r['days_open_or_to_merge'] for r in merged)}")

if __name__ == "__main__":
    main(*sys.argv[1:])
