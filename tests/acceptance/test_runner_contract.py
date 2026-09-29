from __future__ import annotations

import io
import os
import unittest
from pathlib import Path

from tools import hackathon_acceptance

try:
    from .support import AcceptanceCase, acceptance
except ImportError:  # Direct discovery with tests/acceptance as the start directory.
    from support import AcceptanceCase, acceptance


def _failure_method(category: str):
    @acceptance(category, f"SYNTHETIC-{category.upper()}")
    def fail(self) -> None:
        self.fail(f"synthetic {category} failure")

    return fail


class RunnerContractTests(AcceptanceCase):
    @acceptance("assertion", "RUNNER-01")
    def test_failures_keep_their_categories_and_return_nonzero(self) -> None:
        synthetic_type = type(
            "SyntheticFailures",
            (unittest.TestCase,),
            {f"test_{category}": _failure_method(category) for category in hackathon_acceptance.FAILURE_CATEGORIES},
        )
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(synthetic_type)
        stream = io.StringIO()
        report = hackathon_acceptance.run_suite(suite, stream=stream)
        output = stream.getvalue()

        self.assertEqual(report.exit_code, 1)
        self.assertEqual(len(report.records), len(hackathon_acceptance.FAILURE_CATEGORIES))
        for category in hackathon_acceptance.FAILURE_CATEGORIES:
            self.assertIn(f"FAIL [{category.upper():9}]", output)
            self.assertIn(f"{category.upper()}=1", output)
        self.assertIn("SUMMARY PASS=0 FAIL=5 SKIP=0", output)

    @acceptance("assertion", "RUNNER-02")
    def test_pass_and_skip_do_not_mask_or_create_failure(self) -> None:
        class SyntheticPassAndSkip(unittest.TestCase):
            @acceptance("route", "SYNTHETIC-PASS")
            def test_pass(self) -> None:
                self.assertTrue(True)

            @acceptance("network", "SYNTHETIC-SKIP")
            def test_skip(self) -> None:
                self.skipTest("dependency unavailable")

        stream = io.StringIO()
        report = hackathon_acceptance.run_suite(
            unittest.defaultTestLoader.loadTestsFromTestCase(SyntheticPassAndSkip),
            stream=stream,
        )
        output = stream.getvalue()
        self.assertEqual(report.exit_code, 0)
        self.assertIn("SUMMARY PASS=1 FAIL=0 SKIP=1", output)
        self.assertIn("PASS [ROUTE", output)
        self.assertIn("SKIP [NETWORK", output)

    @acceptance("assertion", "RUNNER-03")
    def test_runner_provides_and_cleans_an_isolated_temporary_root(self) -> None:
        observed: dict[str, Path] = {}

        class SyntheticIsolation(unittest.TestCase):
            @acceptance("assertion", "SYNTHETIC-ISOLATION")
            def runTest(self) -> None:
                temporary_root = Path(os.environ["REALTAGS_ACCEPTANCE_TMPDIR"]).resolve()
                observed["root"] = temporary_root
                self.assertTrue(temporary_root.is_dir())
                self.assertNotEqual(temporary_root, hackathon_acceptance.ROOT)
                (temporary_root / "synthetic.sqlite3").touch()

        report = hackathon_acceptance.run_suite(
            unittest.TestSuite([SyntheticIsolation()]),
            stream=io.StringIO(),
        )
        self.assertEqual(report.exit_code, 0)
        self.assertIn("root", observed)
        self.assertFalse(observed["root"].exists())

    @acceptance("assertion", "RUNNER-04")
    def test_dry_run_output_is_deterministic_and_names_all_statuses(self) -> None:
        outputs: list[str] = []
        for _ in range(2):
            stream = io.StringIO()
            exit_code = hackathon_acceptance.main(["--dry-run"], stream=stream)
            self.assertEqual(exit_code, 0)
            outputs.append(stream.getvalue())
        self.assertEqual(outputs[0], outputs[1])
        self.assertIn("PASS", outputs[0])
        self.assertIn("FAIL=0", outputs[0])
        self.assertIn("SKIP", outputs[0])
        self.assertIn("NETWORK=0 INPUT=0 AUTH=0 ROUTE=0 ASSERTION=0", outputs[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
