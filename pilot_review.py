"""Replay the published pilot evidence offline, using only Python's standard library."""
import argparse
import csv
import json
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent / "evidence"


def triage(case):
    before = case["old"]
    after = case["changed"]
    failure = before["upgrade"]
    if failure in (None, "pass"):
        return "Establish the original failure"
    if after["upgrade"] != "pass":
        return "Re-run the same check on the proposed change"
    if case["intervention"] == "source":
        return "Review the source patch on the upgraded branch"
    if case["intervention"] != "runner":
        return "Review intervention manually"
    if before["base"] == failure and after["base"] == "pass":
        return "Test the shared runner change in hosted CI"
    return "Collect matching base-branch controls before attributing the failure"


def outcomes(rows, start, window):
    if window < 1 or start < 0 or start + window > len(rows):
        raise ValueError("The requested window must lie inside the 120 observed days.")
    period = rows[start:start + window]
    at_risk = period[0]["at_risk"]
    merged = sum(row["merged"] for row in period)
    closed = sum(row["closed_unmerged"] for row in period)
    return at_risk, merged, closed, at_risk - merged - closed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", type=int, action="append", help="age landmark (repeatable)")
    parser.add_argument("--window", type=int, default=30, help="days after each landmark")
    args = parser.parse_args()
    with (EVIDENCE / "cohort.csv").open() as stream:
        rows = [{key: int(value) for key, value in r.items()} for r in csv.DictReader(stream)]
    print("Historical outcomes for dependency-bot PRs\n")
    print("Age   Eligible   Merged   Closed unmerged   Still open   Merge fraction")
    for day in (args.day if args.day is not None else [0, 30, 90]):
        try:
            n, merged, closed, remaining = outcomes(rows, day, args.window)
        except ValueError as error:
            parser.error(str(error))
        rate = f"{merged / n:.1%}" if n else "n/a"
        print(f"{day:3}   {n:8}   {merged:6}   {closed:15}   {remaining:10}   {rate:>14}")
    print(f"Outcomes over the following {args.window} days. Same inception cohort; no agent intervention measured.")
    for case in json.loads((EVIDENCE / "cases.json").read_text()):
        print(f"\n{case['name']} | {case['check']}")
        for revision in ("base", "upgrade"):
            old = case["old"][revision] or "unobserved"
            changed = case["changed"][revision] or "unobserved"
            print(f"  {revision:7}  {old} -> {changed}")
        print("  Decision:", triage(case))
        print("  Evidence:", case["record"])
        print("  Limit:", case["limit"])
        print(f"  Inspect: evidence/{case['patch']} | {case['source']}")


if __name__ == "__main__":
    main()
