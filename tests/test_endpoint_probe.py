"""Offline safety and classification tests for endpoint_probe.py."""

from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlsplit

from endpoint_probe import (
    PROBES,
    BodyMeta,
    Probe,
    build_sessions,
    classify_response,
    sanitize_target,
    summarize_body,
    validate_target,
)


class ContractTests(unittest.TestCase):
    def test_contract_has_expected_unique_items(self) -> None:
        self.assertEqual(37, len(PROBES))
        ids = [probe.probe_id for probe in PROBES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_http_targets_are_valid_except_documented_invalid_port(self) -> None:
        invalid = []
        for probe in PROBES:
            issue = validate_target(probe)
            if issue:
                invalid.append(probe.probe_id)
        self.assertEqual(["netease.qr_check_invalid_port"], invalid)

    def test_no_url_contains_userinfo(self) -> None:
        for probe in PROBES:
            if probe.mode != "http":
                continue
            parts = urlsplit(probe.target)
            self.assertIsNone(parts.username, probe.probe_id)
            self.assertIsNone(parts.password, probe.probe_id)

    def test_sensitive_operations_use_safe_probe_actions(self) -> None:
        for probe in PROBES:
            if probe.documented_method != "POST":
                continue
            if probe.read_only_post:
                self.assertEqual("POST", probe.probe_method, probe.probe_id)
            else:
                self.assertIn(probe.probe_method, {"OPTIONS", "NOT_EXECUTED"}, probe.probe_id)

    def test_runtime_guard_rejects_mutations(self) -> None:
        mutation = Probe(
            probe_id="test.mutation",
            platform="Test",
            documented_method="POST",
            target="https://example.test/graphql",
            probe_method="POST",
            source_ref="test",
            json_body={"query": "mutation Unsafe { doThing }"},
            read_only_post=True,
        )
        self.assertIn("read-only", validate_target(mutation) or "")

    def test_daily_checkin_is_never_executed(self) -> None:
        probe = next(item for item in PROBES if item.probe_id == "netease.daily_checkin")
        self.assertEqual("OPTIONS", probe.probe_method)

    def test_steam_probes_never_include_an_api_key(self) -> None:
        for probe in PROBES:
            if not probe.probe_id.startswith("steam."):
                continue
            query = parse_qs(urlsplit(probe.target).query)
            self.assertNotIn("key", query, probe.probe_id)

    def test_local_probes_ignore_environment_proxies(self) -> None:
        remote, local = build_sessions()
        try:
            self.assertTrue(remote.trust_env)
            self.assertFalse(local.trust_env)
        finally:
            local.close()
            remote.close()


class RedactionTests(unittest.TestCase):
    def test_sensitive_query_values_are_redacted(self) -> None:
        target = sanitize_target("https://example.test/x?key=secret-value&type=running")
        self.assertIn("key=%5BREDACTED%5D", target)
        self.assertIn("type=running", target)
        self.assertNotIn("secret-value", target)

    def test_invalid_port_is_not_echoed(self) -> None:
        self.assertEqual("<invalid-target>", sanitize_target("http://localhost:300300/x"))


class ClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.get_probe = Probe(
            probe_id="test.get",
            platform="Test",
            documented_method="GET",
            target="https://example.test/x",
            probe_method="GET",
            source_ref="test",
        )

    def test_successful_json_is_available(self) -> None:
        label, _ = classify_response(self.get_probe, 200, BodyMeta(kind="object"))
        self.assertEqual("AVAILABLE", label)

    def test_auth_is_not_reported_as_unavailable(self) -> None:
        label, _ = classify_response(self.get_probe, 401, BodyMeta(kind="object"))
        self.assertEqual("AUTH_REQUIRED", label)

    def test_body_auth_signal_overrides_http_200(self) -> None:
        body = BodyMeta(kind="object", auth_signal=True, rejected_signal=True)
        label, _ = classify_response(self.get_probe, 200, body)
        self.assertEqual("AUTH_REQUIRED", label)

    def test_resource_404_differs_from_route_404(self) -> None:
        resource_probe = Probe(
            probe_id="test.resource",
            platform="Test",
            documented_method="GET",
            target="https://example.test/items/0",
            probe_method="GET",
            source_ref="test",
            resource_scoped=True,
        )
        route_label, _ = classify_response(self.get_probe, 404, BodyMeta())
        resource_label, _ = classify_response(resource_probe, 404, BodyMeta())
        self.assertEqual("ROUTE_NOT_FOUND", route_label)
        self.assertEqual("RESOURCE_NOT_FOUND", resource_label)

    def test_options_success_is_inconclusive(self) -> None:
        options_probe = Probe(
            probe_id="test.options",
            platform="Test",
            documented_method="POST",
            target="https://example.test/login",
            probe_method="OPTIONS",
            source_ref="test",
        )
        label, _ = classify_response(options_probe, 204, BodyMeta())
        self.assertEqual("INCONCLUSIVE_SAFE_PROBE", label)

    def test_truncated_json_shape_is_not_a_false_negative(self) -> None:
        body = summarize_body(b'[{"id": 1, "large": "unfinished', "application/json", True)
        self.assertEqual("list_truncated", body.kind)
        label, _ = classify_response(self.get_probe, 200, body)
        self.assertEqual("AVAILABLE", label)


if __name__ == "__main__":
    unittest.main()
