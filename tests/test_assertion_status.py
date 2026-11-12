"""SPEC-003: every gateway route has an assertion state (enforce, report, planned with dates, or exempt with a reason)."""

from __future__ import annotations

import datetime
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODES = {"enforce", "report", "planned", "exempt"}


def _date(value: object) -> datetime.date:
    assert isinstance(value, str), value
    return datetime.date.fromisoformat(value)


class AssertionStatus(unittest.TestCase):
    def setUp(self):
        self.routes = json.loads((ROOT / "routes.json").read_text())["routes"]
        self.status = json.loads((ROOT / "assertion-status.json").read_text())["routes"]

    def test_every_route_has_exactly_one_entry(self):
        self.assertEqual(sorted(self.status), sorted(self.routes))

    def test_each_entry_is_complete(self):
        for system, entry in self.status.items():
            with self.subTest(system):
                self.assertIn(entry["mode"], MODES)
                if entry["mode"] == "enforce":
                    _date(entry["since"])
                elif entry["mode"] == "report":
                    self.assertLess(_date(entry["since"]), _date(entry["enforce_review"]))
                elif entry["mode"] == "planned":
                    self.assertLess(_date(entry["report_by"]), _date(entry["enforce_review"]))
                else:
                    self.assertGreater(len(entry.get("reason", "")), 40)


if __name__ == "__main__":
    unittest.main()
