#!/usr/bin/env python3
"""Precision check: for every scoped task, open the repo's real manifest/lock files and
confirm the package name and the vulnerable version are both pinned there."""
import csv
import json
import re
import urllib.request

from inventory import HERE, SSL, gh

MANIFEST = re.compile(r"(^|/)(package\.json|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|requirements[^/]*\.txt|"
                      r"pyproject\.toml|poetry\.lock|Pipfile\.lock|setup\.py|setup\.cfg|uv\.lock|pom\.xml|"
                      r"build\.gradle(\.kts)?|gradle\.lockfile|libs\.versions\.toml|go\.mod|Gemfile\.lock|Cargo\.lock|"
                      r"[^/]*\.csproj|environment[^/]*\.ya?ml)$")


def raw(repo, branch, path):
    try:
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{urllib.request.quote(path)}"
        return urllib.request.urlopen(url, timeout=60, context=SSL).read().decode(errors="ignore")
    except Exception:
        return ""


def main():
    repos = {json.loads(l)["repo"]: json.loads(l) for l in open(HERE / "data/repos.jsonl")}
    scope = {(r["repo"], r["package"]): r for r in csv.DictReader(open(HERE / "out/pilot_scope.csv"))}
    out = []
    for t in sorted((HERE / "out/tasks").glob("*.md")):
        head = t.read_text().splitlines()[0]
        m = re.match(r"# (\S+): upgrade (\S+) (.+) -> (\S+)", head)
        repo, pkg, versions = m[1], m[2], m[3].split(" / ")
        br = repos[repo]["default_branch"]
        tree = gh(f"/repos/{repo}/git/trees/{br}?recursive=1") or {"tree": []}
        files = [x["path"] for x in tree["tree"] if x["type"] == "blob" and MANIFEST.search(x["path"])
                 and "node_modules/" not in x["path"]]
        short = pkg.split(":")[-1]
        hit = ""
        for path in sorted(files, key=lambda p: (p.count("/"), len(p)))[:60]:
            txt = raw(repo, br, path)
            if short.lower() in txt.lower() and any(v in txt for v in versions):
                # name and version on the same or adjacent lines?
                lines = txt.splitlines()
                for i, ln in enumerate(lines):
                    if short.lower() in ln.lower() and any(v in " ".join(lines[i:i + 4]) for v in versions):
                        hit = f"{path}:{i + 1}"
                        break
            if hit:
                break
        out.append({"task": t.name, "repo": repo, "package": pkg, "versions": " / ".join(versions),
                    "manifests_checked": min(len(files), 60), "confirmed_at": hit})
        print(f"{'OK ' if hit else '?? '} {repo:38} {pkg:38} {hit or 'not found in ' + str(min(len(files), 60)) + ' manifests'}", flush=True)
    with open(HERE / "out/verification.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    ok = sum(bool(o["confirmed_at"]) for o in out)
    print(f"confirmed in the repo's own manifest: {ok}/{len(out)}")


if __name__ == "__main__":
    main()
