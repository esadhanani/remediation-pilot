#!/usr/bin/env python3
"""Step 1 of a vulnerability-remediation pilot: inventory.

For each financial-services GitHub org, list active public repos, pull each
repo's dependency SBOM from GitHub's dependency graph, and match every pinned
package version against OSV.dev. Output: data/findings.jsonl (one row per
repo x package x advisory) and data/repos.jsonl (one row per repo scanned).

Only public data is read. Needs a GitHub token (uses `gh auth token`).
"""
import concurrent.futures as cf
import datetime as dt
from functools import lru_cache
import json
import pathlib
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).parent
DATA = HERE / "data"
ORGS = json.loads((HERE / "orgs.json").read_text())
ACTIVE_DAYS = 365
SSL = ssl.create_default_context(cafile="/etc/ssl/cert.pem") if pathlib.Path("/etc/ssl/cert.pem").exists() else None
OSV_ECOSYSTEMS = {
    "npm": "npm", "pypi": "PyPI", "maven": "Maven", "golang": "Go", "cargo": "crates.io",
    "gem": "RubyGems", "nuget": "NuGet", "composer": "Packagist", "pub": "Pub", "hex": "Hex",
}


def http(url, data=None, headers=None, tries=4):
    h = {"User-Agent": "remediation-pilot", "Accept": "application/json"}
    h.update(headers or {})
    body = json.dumps(data).encode() if data is not None else None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers=h)
            with urllib.request.urlopen(req, timeout=90, context=SSL) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (404, 451, 409):
                return None
            if e.code == 403 and "rate limit" in e.read().decode(errors="ignore").lower():
                time.sleep(60)
            else:
                time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return None


@lru_cache(maxsize=1)
def github_token():
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def gh(path):
    return http("https://api.github.com" + path,
                headers={"Authorization": "Bearer " + github_token(), "X-GitHub-Api-Version": "2022-11-28",
                         "Accept": "application/vnd.github+json"})


def list_repos(org):
    out, page = [], 1
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=ACTIVE_DAYS)).isoformat()
    while True:
        rs = gh(f"/orgs/{org}/repos?type=public&per_page=100&page={page}") or []
        for r in rs:
            if r["fork"] or r["archived"] or r["disabled"]:
                continue
            if (r["pushed_at"] or "") < cutoff:
                continue
            out.append({"org": org, "repo": r["full_name"], "stars": r["stargazers_count"],
                        "language": r["language"], "pushed_at": r["pushed_at"],
                        "default_branch": r["default_branch"]})
        if len(rs) < 100:
            return out
        page += 1


def parse_purl(purl):
    # pkg:npm/%40scope/name@1.2.3  ->  (ecosystem, name, version)
    if not purl or not purl.startswith("pkg:") or "@" not in purl:
        return None
    body = purl[4:].split("?")[0].split("#")[0]
    typ, rest = body.split("/", 1)
    name, _, version = rest.rpartition("@")
    name = urllib.request.unquote(name)
    version = urllib.request.unquote(version)
    eco = OSV_ECOSYSTEMS.get(typ)
    if not eco or not version or any(c in version for c in "<>=^~*, "):
        return None  # a range, not a pinned version
    if eco == "Maven":
        name = name.replace("/", ":")
    return eco, name, version


def sbom_packages(repo):
    d = gh(f"/repos/{repo}/dependency-graph/sbom")
    if not d:
        return None
    sb = d.get("sbom", {})
    root = next((r["relatedSpdxElement"] for r in sb.get("relationships", [])
                 if r.get("relationshipType") == "DESCRIBES"), None)
    direct = {r["relatedSpdxElement"] for r in sb.get("relationships", [])
              if r.get("relationshipType") == "DEPENDS_ON" and r.get("spdxElementId") == root}
    pk = {}
    for p in sb.get("packages", []):
        purl = next((x["referenceLocator"] for x in p.get("externalRefs", [])
                     if x.get("referenceType") == "purl"), None)
        parsed = parse_purl(purl)
        if parsed:
            pk[parsed] = pk.get(parsed, False) or (p.get("SPDXID") in direct)
    return pk


def osv_batch(pkgs):
    """pkgs: list of (eco, name, version) -> list of lists of vuln ids."""
    res = []
    for i in range(0, len(pkgs), 500):
        chunk = pkgs[i:i + 500]
        q = {"queries": [{"package": {"ecosystem": e, "name": n}, "version": v} for e, n, v in chunk]}
        response = http("https://api.osv.dev/v1/querybatch", data=q)
        results = response.get("results") if isinstance(response, dict) else None
        if not isinstance(results, list) or len(results) != len(chunk):
            raise RuntimeError("Incomplete advisory response; inventory snapshot was not written.")
        for result in results:
            if not isinstance(result, dict) or "error" in result:
                raise RuntimeError("Invalid advisory result; inventory snapshot was not written.")
            res.append([v["id"] for v in result.get("vulns", [])])
    return res


def scan_repo(meta):
    pk = sbom_packages(meta["repo"])
    if pk is None:
        return {**meta, "sbom": False, "packages": 0}, []
    keys = list(pk)
    hits = osv_batch(keys) if keys else []
    rows = []
    for key, ids in zip(keys, hits):
        for vid in ids:
            rows.append({"repo": meta["repo"], "org": meta["org"], "ecosystem": key[0],
                         "package": key[1], "version": key[2], "direct": pk[key], "vuln": vid})
    return {**meta, "sbom": True, "packages": len(keys)}, rows


def main():
    DATA.mkdir(exist_ok=True)
    repos = []
    for o in ORGS:
        rs = list_repos(o["org"])
        print(f"{o['org']:18} active public repos: {len(rs)}", flush=True)
        repos += rs
    done_r, done_f = [], []
    with cf.ThreadPoolExecutor(8) as ex:
        for i, (meta, rows) in enumerate(ex.map(scan_repo, repos), 1):
            done_r.append(meta)
            done_f += rows
            if i % 50 == 0:
                print(f"scanned {i}/{len(repos)} repos, {len(done_f)} raw findings", flush=True)
    (DATA / "repos.jsonl").write_text("\n".join(json.dumps(r) for r in done_r))
    (DATA / "findings.jsonl").write_text("\n".join(json.dumps(r) for r in done_f))
    print(f"done: {len(done_r)} repos, {sum(r['sbom'] for r in done_r)} with SBOM, {len(done_f)} raw findings")


if __name__ == "__main__":
    sys.exit(main())
