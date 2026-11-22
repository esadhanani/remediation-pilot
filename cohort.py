"""Summarise 120 days of dependency-bot PR history from an existing snapshot."""

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Closed-PR queries covered one year; take complete UTC days inside that window.
START = datetime(2025, 11, 20, tzinfo=timezone.utc)
CUTOFF = datetime(2026, 11, 19, tzinfo=timezone.utc)
HORIZON = 120
BINS = ("merged", "closed_unmerged")


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def make_table(records):
    counts = Counter()
    query_sizes = Counter()
    seen = set()
    rows = []
    for row in records:
        key = row["repo"].lower(), row["number"]
        if key in seen:
            raise ValueError(f"Duplicate PR in snapshot: {key}")
        seen.add(key)
        query = (row["org"].lower(), row["bot"], row["state"])
        query_sizes[query] += 1
        rows.append(row)

    # If either bot's open or closed query reached GitHub's search cap,
    # omit that organisation from both sides of every comparison.
    excluded = {org for (org, _, _), size in query_sizes.items() if size >= 1000}
    latest_open = CUTOFF - timedelta(days=HORIZON)
    n = 0
    for row in rows:
        opened = timestamp(row["created"])
        if row["org"].lower() in excluded or not START <= opened < latest_open:
            continue
        n += 1
        if row["closed"]:
            age = (timestamp(row["closed"]) - opened).days
            if age < 0:
                raise ValueError("Close predates open")
            if age < HORIZON:
                outcome = "merged" if row["merged"] else "closed_unmerged"
                counts[age, outcome] += 1
    table = []
    for day in range(HORIZON):
        merged, closed = [counts[day, key] for key in BINS]
        table.append((day, n, merged, closed))
        n -= merged + closed
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="bot_prs.jsonl from the Nov 19 pilot")
    args = parser.parse_args()
    with args.snapshot.open() as source:
        table = make_table(json.loads(line) for line in source if line.strip())
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["age_days", "at_risk", *BINS])
    writer.writerows(table)


if __name__ == "__main__":
    main()
