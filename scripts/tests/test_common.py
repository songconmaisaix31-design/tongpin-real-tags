import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from common import path_matches, pattern_within, patterns_overlap, run, validate_plan  # noqa: E402


class ProcessTests(unittest.TestCase):
    def test_run_decodes_utf8_output(self):
        cp = run(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(bytes.fromhex('e29c93'))",
            ]
        )
        self.assertEqual(cp.stdout, "\u2713")


class PatternTests(unittest.TestCase):
    def test_directory_glob(self):
        self.assertTrue(path_matches("apps/web/src/App.tsx", "apps/web/**"))
        self.assertFalse(path_matches("services/api/app.py", "apps/web/**"))

    def test_containment(self):
        self.assertTrue(pattern_within("apps/web/src/**", "apps/web/**"))
        self.assertFalse(pattern_within("apps/**", "apps/web/**"))

    def test_overlap(self):
        self.assertTrue(patterns_overlap("apps/web/**", "apps/web/src/**"))
        self.assertFalse(patterns_overlap("apps/web/**", "services/api/**"))


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.cfg = json.loads((root / ".agents/fleet.json").read_text(encoding="utf-8"))
        cls.plan = json.loads((root / ".agents/plans/hackathon-prize.json").read_text(encoding="utf-8"))

    def test_project_plan_is_valid(self):
        self.assertEqual(validate_plan(self.plan, self.cfg), [])

    def test_parallel_overlap_is_rejected(self):
        plan = json.loads(json.dumps(self.plan))
        first = plan["waves"][1]["tasks"][0]
        second = plan["waves"][1]["tasks"][1]
        second["track"] = first["track"]
        second["write_paths"] = list(first["write_paths"])
        errors = validate_plan(plan, self.cfg)
        self.assertTrue(any("appears twice" in error or "overlap" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
