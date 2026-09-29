"""Offline acceptance runner for the RealTags hackathon candidate."""

from __future__ import annotations

import argparse
import os
import socket
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence, TextIO
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_DIR = ROOT / "tests" / "acceptance"
FAILURE_CATEGORIES = ("network", "input", "auth", "route", "assertion")
STATUSES = ("PASS", "FAIL", "SKIP")


@dataclass(frozen=True)
class CaseRecord:
    status: str
    category: str
    control: str
    test_id: str
    detail: str = ""
    traceback: str = ""


@dataclass(frozen=True)
class RunReport:
    records: tuple[CaseRecord, ...]
    exit_code: int


def case_metadata(test: unittest.TestCase) -> tuple[str, str]:
    method_name = getattr(test, "_testMethodName", "runTest")
    method = getattr(test, method_name, None)
    category = getattr(method, "acceptance_category", "assertion")
    control = getattr(method, "acceptance_control", "UNMAPPED")
    return category, control


def short_error(result: unittest.TestResult, error, test: unittest.TestCase) -> tuple[str, str]:
    rendered = result._exc_info_to_string(error, test)
    lines = [line.strip() for line in rendered.splitlines() if line.strip()]
    return (lines[-1] if lines else error[0].__name__), rendered


class AcceptanceResult(unittest.TestResult):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[CaseRecord] = []

    def _record(
        self,
        test: unittest.TestCase,
        status: str,
        detail: str = "",
        traceback: str = "",
        suffix: str = "",
    ) -> None:
        category, control = case_metadata(test)
        test_id = test.id() + suffix
        self.records.append(CaseRecord(status, category, control, test_id, detail, traceback))

    def addSuccess(self, test: unittest.TestCase) -> None:
        super().addSuccess(test)
        self._record(test, "PASS")

    def addFailure(self, test: unittest.TestCase, err) -> None:
        super().addFailure(test, err)
        detail, traceback = short_error(self, err, test)
        self._record(test, "FAIL", detail, traceback)

    def addError(self, test: unittest.TestCase, err) -> None:
        super().addError(test, err)
        detail, traceback = short_error(self, err, test)
        self._record(test, "FAIL", detail, traceback)

    def addSkip(self, test: unittest.TestCase, reason: str) -> None:
        super().addSkip(test, reason)
        self._record(test, "SKIP", reason)

    def addExpectedFailure(self, test: unittest.TestCase, err) -> None:
        super().addExpectedFailure(test, err)
        detail, traceback = short_error(self, err, test)
        self._record(test, "SKIP", f"expected failure: {detail}", traceback)

    def addUnexpectedSuccess(self, test: unittest.TestCase) -> None:
        super().addUnexpectedSuccess(test)
        self._record(test, "FAIL", "unexpected success")

    def addSubTest(self, test: unittest.TestCase, subtest: unittest.TestCase, err) -> None:
        super().addSubTest(test, subtest, err)
        if err is None:
            return
        detail, traceback = short_error(self, err, test)
        self._record(test, "FAIL", detail, traceback, suffix=f" {subtest}")


def iter_tests(suite: unittest.TestSuite) -> Iterable[unittest.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_tests(item)
        else:
            yield item


def build_suite() -> unittest.TestSuite:
    root_path = str(ROOT)
    acceptance_path = str(ACCEPTANCE_DIR)
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    if acceptance_path not in sys.path:
        sys.path.insert(0, acceptance_path)
    return unittest.defaultTestLoader.discover(acceptance_path, pattern="test_*.py")


def validate_manifest(suite: unittest.TestSuite) -> list[str]:
    errors: list[str] = []
    for test in iter_tests(suite):
        category, control = case_metadata(test)
        if category not in FAILURE_CATEGORIES:
            errors.append(f"{test.id()}: unknown category {category!r}")
        if control == "UNMAPPED":
            errors.append(f"{test.id()}: missing acceptance control")
    return errors


def print_report(records: Sequence[CaseRecord], stream: TextIO, *, verbose: bool) -> None:
    for record in records:
        line = f"{record.status:<4} [{record.category.upper():9}] {record.control:<18} {record.test_id}"
        if record.detail:
            line += f" :: {record.detail}"
        print(line, file=stream)
        if verbose and record.status == "FAIL" and record.traceback:
            for traceback_line in record.traceback.rstrip().splitlines():
                print(f"      {traceback_line}", file=stream)

    counts = {status: sum(record.status == status for record in records) for status in STATUSES}
    failure_counts = {
        category: sum(record.status == "FAIL" and record.category == category for record in records)
        for category in FAILURE_CATEGORIES
    }
    print(
        "SUMMARY " + " ".join(f"{status}={counts[status]}" for status in STATUSES),
        file=stream,
    )
    print(
        "FAIL_BY_CATEGORY "
        + " ".join(f"{category.upper()}={failure_counts[category]}" for category in FAILURE_CATEGORIES),
        file=stream,
    )


def run_suite(
    suite: unittest.TestSuite,
    *,
    stream: TextIO,
    verbose: bool = False,
    require_assembly: bool = False,
) -> RunReport:
    result = AcceptanceResult()
    environment = {
        "REALTAGS_ACCEPTANCE_OFFLINE": "1",
        "REALTAGS_ACCEPTANCE_REQUIRE_ASSEMBLY": "1" if require_assembly else "0",
    }
    with tempfile.TemporaryDirectory(prefix="realtags-acceptance-") as temporary_root:
        environment["REALTAGS_ACCEPTANCE_TMPDIR"] = temporary_root
        with (
            mock.patch.dict(os.environ, environment, clear=False),
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=OSError("external network disabled by acceptance runner"),
            ),
        ):
            suite.run(result)

    print_report(result.records, stream, verbose=verbose)
    exit_code = 0 if all(record.status != "FAIL" for record in result.records) else 1
    return RunReport(tuple(result.records), exit_code)


def render_dry_run(suite: unittest.TestSuite, stream: TextIO) -> int:
    tests = list(iter_tests(suite))
    records = [
        CaseRecord(
            "PASS",
            "assertion",
            "RUNNER-MANIFEST",
            "runner.contract",
            "manifest loaded; statuses PASS/FAIL/SKIP; offline execution deferred",
        )
    ]
    for test in tests:
        category, control = case_metadata(test)
        records.append(CaseRecord("SKIP", category, control, test.id(), "dry-run: not executed"))
    print("MODE DRY-RUN (deterministic manifest; no tests or network executed)", file=stream)
    print_report(records, stream, verbose=False)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the offline RealTags hackathon acceptance suite against disposable SQLite databases."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and print the deterministic PASS/FAIL/SKIP manifest without executing cases",
    )
    parser.add_argument(
        "--require-assembly",
        action="store_true",
        help="treat missing target datasource route/schema dependencies as failures",
    )
    parser.add_argument("--verbose", action="store_true", help="print full tracebacks for failed cases")
    return parser


def main(argv: Sequence[str] | None = None, *, stream: TextIO | None = None) -> int:
    output = stream or sys.stdout
    args = build_parser().parse_args(argv)
    suite = build_suite()
    manifest_errors = validate_manifest(suite)
    if manifest_errors:
        records = [
            CaseRecord("FAIL", "assertion", "RUNNER-MANIFEST", "runner.contract", error)
            for error in manifest_errors
        ]
        print_report(records, output, verbose=args.verbose)
        return 2
    if args.dry_run:
        return render_dry_run(suite, output)
    return run_suite(
        suite,
        stream=output,
        verbose=args.verbose,
        require_assembly=args.require_assembly,
    ).exit_code


if __name__ == "__main__":
    raise SystemExit(main())
