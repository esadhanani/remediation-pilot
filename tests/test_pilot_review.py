import csv
import unittest
from datetime import timedelta

from cohort import HORIZON, START, make_table
from pilot_review import EVIDENCE, outcomes


def request(number, age=None, merged=False, opened=START, org="team"):
    return {"repo": f"{org}/demo", "number": number, "org": org, "bot": "bot",
            "state": "closed" if age is not None else "open", "created": opened.isoformat(),
            "closed": (opened + timedelta(days=age)).isoformat() if age is not None else None,
            "merged": merged}


class CohortTests(unittest.TestCase):
    def test_half_open_intervals_and_competing_closure(self):
        table = make_table([request(1, 29.99, True), request(2, 30, True),
                            request(3, 29, False), request(4), request(5, HORIZON, True)])
        self.assertEqual(table[0][1], 5)
        self.assertEqual(table[29], (29, 5, 1, 1))
        self.assertEqual(table[30], (30, 3, 1, 0))
        self.assertEqual(table[-1][1], 2)

    def test_exclusions(self):
        rows = [request(i, org="capped") for i in range(1000)]
        rows.extend([request(1000, 5, True, org="capped"), request(1),
                     request(2, opened=START-timedelta(seconds=1)),
                     request(3, opened=START+timedelta(days=300))])
        self.assertEqual(make_table(rows)[0][1], 1)

    def test_duplicates(self):
        with self.assertRaises(ValueError):
            make_table([request(1), request(1)])

    def test_published_table_and_conservation(self):
        with (EVIDENCE / "cohort.csv").open() as stream:
            rows = [{k: int(v) for k, v in r.items()} for r in csv.DictReader(stream)]
        self.assertEqual([r["age_days"] for r in rows], list(range(HORIZON)))
        for left, right in zip(rows, rows[1:]):
            self.assertEqual(left["at_risk"] - left["merged"] - left["closed_unmerged"], right["at_risk"])
        self.assertEqual(outcomes(rows, 30, 30), (335, 19, 46, 270))
        with self.assertRaises(ValueError):
            outcomes(rows, 100, 30)
