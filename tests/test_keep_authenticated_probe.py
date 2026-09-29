"""Offline security tests for the interactive Keep authenticated probe."""

from __future__ import annotations

import inspect
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import requests

import keep_authenticated_probe as probe

SENTINEL = "sentinel-secret-value-0123456789"


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        body: bytes,
        content_type: str = "application/json",
    ) -> None:
        self.status_code = status_code
        self.body = body
        self.headers = {"Content-Type": content_type}
        self.closed = False

    def iter_content(self, chunk_size: int = 1024):
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset : offset + chunk_size]

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict] = []
        self.cookies = requests.cookies.RequestsCookieJar()

    def request(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class InputBoundaryTests(unittest.TestCase):
    def test_cli_accepts_no_arguments(self) -> None:
        self.assertTrue(probe.validate_cli_args([]))
        self.assertFalse(probe.validate_cli_args(["--token", SENTINEL]))

    def test_rejected_cli_secret_is_not_echoed(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = probe.main(["--token", SENTINEL])
        combined = stdout.getvalue() + stderr.getvalue()
        self.assertEqual(2, code)
        self.assertNotIn(SENTINEL, combined)

    def test_token_shape_validation(self) -> None:
        self.assertEqual(SENTINEL, probe.validate_token(SENTINEL))
        with self.assertRaises(ValueError):
            probe.validate_token("short")
        with self.assertRaises(ValueError):
            probe.validate_token(f"Bearer {SENTINEL}")
        with self.assertRaises(ValueError):
            probe.validate_token(f" {SENTINEL}")

    def test_non_tty_is_rejected(self) -> None:
        with patch.object(probe.sys.stdin, "isatty", return_value=False):
            with self.assertRaises(RuntimeError):
                probe.require_private_tty()

    def test_source_does_not_read_credential_files_or_environment(self) -> None:
        source = inspect.getsource(probe)
        self.assertNotIn("load_credentials", source)
        self.assertNotIn("credentials.json", source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("getenv(", source)


class TransportPolicyTests(unittest.TestCase):
    def test_authenticated_session_ignores_environment_and_clears_secret(self) -> None:
        session = probe.build_session(SENTINEL)
        try:
            self.assertFalse(session.trust_env)
            self.assertEqual(f"Bearer {SENTINEL}", session.headers["Authorization"])
        finally:
            probe.close_session(session)
        self.assertNotIn("Authorization", session.headers)

    def test_request_uses_exact_read_only_allowlist(self) -> None:
        response = FakeResponse(200, b'{"ok":true,"data":{"distance":123}}')
        session = FakeSession(response)
        result = probe.probe_sport(session, "running")
        self.assertEqual("AUTHENTICATED_AVAILABLE", result.label)
        self.assertEqual(1, len(session.calls))
        call = session.calls[0]
        self.assertEqual("GET", call["method"])
        self.assertEqual("https://api.gotokeep.com/pd/v3/stats/detail", call["url"])
        self.assertEqual({"dateUnit": "all", "type": "running"}, call["params"])
        self.assertEqual((5, 8), call["timeout"])
        self.assertFalse(call["allow_redirects"])
        self.assertTrue(call["stream"])
        self.assertTrue(call["verify"])
        self.assertTrue(response.closed)

    def test_response_cookie_state_is_cleared_before_the_next_probe(self) -> None:
        session = FakeSession(FakeResponse(200, b'{"ok":true,"data":{}}'))
        session.cookies.set("private-session", SENTINEL)
        probe.probe_sport(session, "running")
        self.assertEqual([], list(session.cookies))

    def test_non_allowlisted_sport_is_rejected_before_request(self) -> None:
        session = FakeSession(FakeResponse(200, b"{}"))
        with self.assertRaises(ValueError):
            probe.probe_sport(session, "hiking")
        self.assertEqual([], session.calls)

    def test_network_exception_text_is_never_retained(self) -> None:
        session = FakeSession(requests.ConnectionError(f"network error {SENTINEL}"))
        session.cookies.set("private-session", SENTINEL)
        result = probe.probe_sport(session, "cycling")
        serialized = json.dumps(result.to_dict())
        self.assertEqual("NETWORK_ERROR", result.label)
        self.assertNotIn(SENTINEL, serialized)
        self.assertEqual([], list(session.cookies))


class ResponseRedactionTests(unittest.TestCase):
    def test_private_response_values_and_keys_do_not_reach_result(self) -> None:
        raw = json.dumps(
            {
                "ok": True,
                "data": {
                    "email": SENTINEL,
                    "routePoints": [SENTINEL],
                    "heartRate": "private-heart-rate-188",
                },
            }
        ).encode()
        session = FakeSession(FakeResponse(200, raw))
        result = probe.probe_sport(session, "running")
        serialized = json.dumps(result.to_dict())
        self.assertEqual("AUTHENTICATED_AVAILABLE", result.label)
        self.assertTrue(result.envelope.data_object_non_empty)
        for forbidden in (
            SENTINEL,
            "email",
            "routePoints",
            "heartRate",
            "private-heart-rate-188",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_untrusted_content_type_is_normalized_before_reporting(self) -> None:
        response = FakeResponse(
            200,
            b'{"ok":true,"data":{}}',
            content_type=f"application/json; private={SENTINEL}",
        )
        result = probe.probe_sport(FakeSession(response), "running")
        serialized = json.dumps(result.to_dict())
        self.assertEqual("application/json", result.content_type)
        self.assertNotIn(SENTINEL, serialized)

    def test_auth_error_code_becomes_fixed_label_only(self) -> None:
        raw = b'{"ok":false,"errorCode":100010,"text":"private server text"}'
        session = FakeSession(FakeResponse(200, raw))
        result = probe.probe_sport(session, "running")
        serialized = json.dumps(result.to_dict())
        self.assertEqual("AUTH_INVALID_OR_EXPIRED", result.label)
        self.assertNotIn("100010", serialized)
        self.assertNotIn("private server text", serialized)

    def test_permission_error_is_not_mislabeled_as_invalid_token(self) -> None:
        raw = b'{"ok":false,"errorCode":403,"text":"private server text"}'
        http_forbidden = probe.probe_sport(FakeSession(FakeResponse(403, raw)), "running")
        enveloped_forbidden = probe.probe_sport(FakeSession(FakeResponse(200, raw)), "running")
        self.assertEqual("PERMISSION_INSUFFICIENT", http_forbidden.label)
        self.assertEqual("PERMISSION_INSUFFICIENT", enveloped_forbidden.label)
        serialized = json.dumps(enveloped_forbidden.to_dict())
        self.assertNotIn("errorCode", serialized)
        self.assertNotIn("private server text", serialized)

    def test_request_validation_failures_have_a_distinct_label(self) -> None:
        raw = json.dumps({"ok": False, "private": SENTINEL}).encode()
        for status_code in (400, 422):
            with self.subTest(status_code=status_code):
                result = probe.probe_sport(
                    FakeSession(FakeResponse(status_code, raw)),
                    "running",
                )
                serialized = json.dumps(result.to_dict())
                self.assertEqual("REQUEST_REJECTED", result.label)
                self.assertNotIn(SENTINEL, serialized)

    def test_truncated_body_is_not_parsed(self) -> None:
        raw = b'{"ok":true,"data":{"private":"' + (b"x" * probe.MAX_RESPONSE_BYTES)
        response = FakeResponse(200, raw)
        session = FakeSession(response)
        result = probe.probe_sport(session, "cycling")
        self.assertTrue(result.envelope.response_truncated)
        self.assertEqual("UNEXPECTED_RESPONSE", result.label)

    def test_status_classification(self) -> None:
        empty = probe.EnvelopeFacts()
        self.assertEqual("AUTH_INVALID_OR_EXPIRED", probe.classify(401, empty)[0])
        self.assertEqual("PERMISSION_INSUFFICIENT", probe.classify(403, empty)[0])
        self.assertEqual("REQUEST_REJECTED", probe.classify(400, empty)[0])
        self.assertEqual("REQUEST_REJECTED", probe.classify(422, empty)[0])
        self.assertEqual("ROUTE_NOT_FOUND", probe.classify(404, empty)[0])
        self.assertEqual("RATE_LIMITED", probe.classify(429, empty)[0])
        self.assertEqual("SERVICE_ERROR", probe.classify(503, empty)[0])

    def test_report_contains_only_sanitized_capability_evidence(self) -> None:
        raw = json.dumps({"ok": True, "data": {"private": SENTINEL}}).encode()
        result = probe.probe_sport(FakeSession(FakeResponse(200, raw)), "running")
        report = probe.build_report([result])
        serialized = json.dumps(report)
        self.assertTrue(report["summary"]["authenticatedAggregateAccess"])
        self.assertNotIn(SENTINEL, serialized)
        self.assertNotIn("private", serialized)

    def test_report_path_is_unique_and_stays_under_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(probe, "REPORT_DIR", Path(directory)):
                path = probe.write_report(probe.build_report([]))
                self.assertEqual(Path(directory).resolve(), path.parent.resolve())
                self.assertTrue(path.exists())


class InteractiveFlowTests(unittest.TestCase):
    def test_interactive_flow_never_prints_token(self) -> None:
        success = probe.AuthenticatedProbeResult(
            probe_id="keep.stats_detail.running",
            method="GET",
            host="api.gotokeep.com",
            path=probe.STATS_PATH,
            query_names=("dateUnit", "type"),
            label="AUTHENTICATED_AVAILABLE",
            reason="Fixed reason.",
            status_code=200,
            latency_ms=1,
            content_type="application/json",
            envelope=probe.EnvelopeFacts(
                top_level_object=True,
                keep_envelope_detected=True,
                success_flag=True,
                data_object_present=True,
                data_object_non_empty=True,
            ),
        )
        stdout = io.StringIO()
        with (
            patch.object(probe, "require_private_tty"),
            patch("builtins.input", return_value=probe.CONFIRMATION_PHRASE),
            patch.object(probe.getpass, "getpass", return_value=SENTINEL),
            patch.object(probe, "probe_sport", return_value=success),
            patch.object(probe, "write_report", return_value=Path("reports/safe.json")),
            redirect_stdout(stdout),
        ):
            code = probe.run_interactive()
        self.assertEqual(0, code)
        self.assertNotIn(SENTINEL, stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
