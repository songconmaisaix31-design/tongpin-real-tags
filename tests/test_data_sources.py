from __future__ import annotations

import json
import socket
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from app import create_app
from app.config import Config
from app.db import get_db
from app.services.adapters import get_source_registry, sync_source
from app.services.data_sources.duolingo import DuolingoAdapter
from app.services.data_sources.fixtures import offline_fixture_tags
from app.services.data_sources.github import GitHubAdapter
from app.services.data_sources.http import JsonRequest, request_json
from app.services.data_sources.leetcode import LeetCodeComAdapter, QUERY
from app.services.data_sources.models import SourceFailure


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "data_sources"
FIXED_TIME = "2026-08-23T00:00:00Z"
LATER_TIME = "2026-08-23T00:01:00Z"


def load_fixture(name: str) -> object:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


class QueueTransport:
    def __init__(self, *responses: object):
        self._responses = list(responses)
        self.requests: list[JsonRequest] = []

    def __call__(self, request: JsonRequest) -> object:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("Unexpected network call")
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FailIfCalledTransport:
    def __init__(self):
        self.calls = 0

    def __call__(self, request: JsonRequest) -> object:
        self.calls += 1
        raise AssertionError(f"Network must not be called for {request.url}")


class FakeResponse:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None):
        self._body = body
        self.headers = headers or {}
        self.read_calls = 0

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None

    def read(self, amount: int = -1) -> bytes:
        self.read_calls += 1
        return self._body if amount < 0 else self._body[:amount]


class FakeOpener:
    def __init__(self, outcome: FakeResponse | BaseException):
        self._outcome = outcome
        self.calls: list[tuple[object, float]] = []

    def open(self, request: object, timeout: float) -> FakeResponse:
        self.calls.append((request, timeout))
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome


class AdapterMappingTests(unittest.TestCase):
    def test_duolingo_maps_only_frozen_public_fields(self) -> None:
        transport = QueueTransport(load_fixture("duolingo_profile.json"))
        result = DuolingoAdapter(
            transport=transport,
            clock=lambda: FIXED_TIME,
            timeout_seconds=3.0,
        ).fetch(" duo ")

        self.assertEqual(result.state, "ready")
        self.assertEqual(result.data_mode, "public_live")
        self.assertEqual(result.fetched_at, FIXED_TIME)
        self.assertEqual(len(transport.requests), 1)
        request = transport.requests[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.timeout_seconds, 3.0)
        self.assertEqual(request.max_bytes, 64 * 1024)
        self.assertTrue(request.url.endswith("?username=duo"))
        self.assertIsNone(request.body)

        tags = {tag.tag_id: tag for tag in result.tags}
        self.assertEqual(
            set(tags),
            {
                "learning_languages",
                "learning_streak",
                "learning_total_xp",
                "learning_course_xp",
                "learning_current_course",
            },
        )
        self.assertEqual(
            tags["learning_languages"].value,
            {"items": ["en", "ja"], "titles": {"en": "English", "ja": "Japanese"}},
        )
        self.assertEqual(tags["learning_streak"].value, {"days": 321})
        self.assertEqual(tags["learning_total_xp"].value, {"xp": 12345})
        self.assertEqual(
            tags["learning_course_xp"].value,
            {"items": [{"language": "en", "xp": 7345}, {"language": "ja", "xp": 5000}]},
        )
        self.assertEqual(
            tags["learning_current_course"].value,
            {"course_id": "course-ja", "language": "ja", "xp": 5000},
        )
        self.assertTrue(all(tag.verified for tag in result.tags))
        self.assertTrue(all(tag.visibility == "self_only" for tag in result.tags))
        self.assertNotIn("learning_consistency", tags)
        self.assertNotIn("learning_active_hours", tags)
        self.assertNotIn("learning_level", tags)

    def test_github_maps_bounded_public_repository_and_event_samples(self) -> None:
        transport = QueueTransport(
            load_fixture("github_user.json"),
            load_fixture("github_repositories.json"),
            load_fixture("github_events.json"),
        )
        result = GitHubAdapter(transport=transport, clock=lambda: FIXED_TIME).fetch("octocat")

        self.assertEqual(result.state, "ready")
        self.assertEqual(len(transport.requests), 3)
        self.assertEqual(
            [request.method for request in transport.requests],
            ["GET", "GET", "GET"],
        )
        self.assertIn("per_page=10&page=1", transport.requests[1].url)
        self.assertIn("per_page=10&page=1", transport.requests[2].url)
        tags = {tag.tag_id: tag for tag in result.tags}
        self.assertEqual(tags["coding_public_repositories"].value, {"count": 12})
        self.assertEqual(
            tags["coding_primary_languages"].value,
            {
                "items": ["Python", "TypeScript"],
                "sample_size": 3,
                "window": "latest_10_owner_repositories",
            },
        )
        self.assertEqual(
            tags["coding_recent_event_types"].value,
            {
                "counts": {"PushEvent": 2, "WatchEvent": 1},
                "event_count": 3,
                "window": "latest_10_public_events",
            },
        )
        self.assertEqual(
            tags["coding_recent_activity_days"].value,
            {"days": 1, "event_count": 3, "window": "latest_10_public_events"},
        )
        self.assertEqual(tags["coding_recent_activity_days"].evidence_kind, "derived")

    def test_github_empty_public_collections_are_ready(self) -> None:
        transport = QueueTransport(
            {"login": "empty-user", "public_repos": 0},
            [],
            [],
        )
        result = GitHubAdapter(transport=transport, clock=lambda: FIXED_TIME).fetch("empty-user")

        self.assertEqual(result.state, "ready")
        tags = {tag.tag_id: tag for tag in result.tags}
        self.assertNotIn("coding_primary_languages", tags)
        self.assertEqual(tags["coding_recent_event_types"].value["event_count"], 0)
        self.assertEqual(tags["coding_recent_activity_days"].value["days"], 0)

    def test_leetcode_uses_the_frozen_query_and_graphql_variable(self) -> None:
        transport = QueueTransport(load_fixture("leetcode_profile.json"))
        result = LeetCodeComAdapter(transport=transport, clock=lambda: FIXED_TIME).fetch(
            "example_user"
        )

        self.assertEqual(result.state, "ready")
        self.assertEqual(len(transport.requests), 1)
        request = transport.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url, "https://leetcode.com/graphql")
        self.assertEqual(request.max_bytes, 32 * 1024)
        self.assertEqual(request.headers, (("Content-Type", "application/json"),))
        body = json.loads((request.body or b"").decode("utf-8"))
        self.assertEqual(body["operationName"], "PublicProfile")
        self.assertEqual(body["query"], QUERY)
        self.assertEqual(body["variables"], {"username": "example_user"})
        self.assertNotIn("example_user", body["query"])

        tags = {tag.tag_id: tag for tag in result.tags}
        self.assertEqual(tags["coding_solved_total"].value, {"count": 300})
        self.assertEqual(
            tags["coding_solved_by_difficulty"].value,
            {"easy": 140, "medium": 120, "hard": 40},
        )
        self.assertEqual(
            tags["coding_accepted_submissions"].value,
            {"total": 720, "easy": 280, "medium": 320, "hard": 120},
        )
        self.assertEqual(tags["coding_public_ranking"].value, {"rank": 4242})

    def test_invalid_handles_never_call_transport(self) -> None:
        cases = (
            (DuolingoAdapter, "bad handle"),
            (GitHubAdapter, "-bad"),
            (GitHubAdapter, "bad-"),
            (LeetCodeComAdapter, "bad.handle"),
        )
        for adapter_type, handle in cases:
            with self.subTest(adapter=adapter_type.__name__, handle=handle):
                transport = FailIfCalledTransport()
                result = adapter_type(transport=transport, clock=lambda: FIXED_TIME).fetch(handle)
                self.assertEqual(result.state, "invalid_input")
                self.assertEqual(result.error_code, "invalid_handle")
                self.assertEqual(result.tags, ())
                self.assertEqual(transport.calls, 0)

        transport = FailIfCalledTransport()
        result = DuolingoAdapter(transport=transport, clock=lambda: FIXED_TIME).fetch("  ")
        self.assertEqual((result.state, result.error_code), ("invalid_input", "missing_handle"))
        self.assertEqual(transport.calls, 0)

    def test_missing_and_malformed_profiles_have_stable_states(self) -> None:
        not_found = DuolingoAdapter(
            transport=QueueTransport({"users": []}),
            clock=lambda: FIXED_TIME,
        ).fetch("missing")
        self.assertEqual((not_found.state, not_found.error_code), ("unavailable", "profile_not_found"))

        malformed_cases = (
            DuolingoAdapter(
                transport=QueueTransport({"users": [{"streak": True, "totalXp": 10, "courses": []}]}),
                clock=lambda: FIXED_TIME,
            ).fetch("duo"),
            GitHubAdapter(
                transport=QueueTransport(
                    {"login": "octocat", "public_repos": 1},
                    [{"fork": False, "language": "Python"}],
                    [],
                ),
                clock=lambda: FIXED_TIME,
            ).fetch("octocat"),
            LeetCodeComAdapter(
                transport=QueueTransport(
                    {
                        "data": {
                            "matchedUser": {
                                "profile": {"ranking": 1},
                                "submitStatsGlobal": {
                                    "acSubmissionNum": [
                                        {"difficulty": "All", "count": 1, "submissions": 1}
                                    ]
                                },
                            }
                        }
                    }
                ),
                clock=lambda: FIXED_TIME,
            ).fetch("leetcode"),
        )
        for result in malformed_cases:
            with self.subTest(source=result.source):
                self.assertEqual(result.state, "malformed_response")
                self.assertEqual(result.error_code, "schema_mismatch")
                self.assertEqual(result.tags, ())

    def test_expected_transport_failures_become_bounded_result_envelopes(self) -> None:
        failures = (
            SourceFailure("timeout", "request_timeout", retryable=True),
            SourceFailure("malformed_response", "response_too_large"),
            SourceFailure("malformed_response", "invalid_json"),
            SourceFailure("upstream_error", "rate_limited", retryable=True),
            SourceFailure("upstream_error", "http_5xx", retryable=True),
        )
        for failure in failures:
            with self.subTest(code=failure.code):
                result = DuolingoAdapter(
                    transport=QueueTransport(failure),
                    clock=lambda: FIXED_TIME,
                ).fetch("duo")
                self.assertEqual(result.state, failure.state)
                self.assertEqual(result.error_code, failure.code)
                self.assertEqual(result.retryable, failure.retryable)
                self.assertIsNone(result.fetched_at)
                self.assertEqual(result.tags, ())
                self.assertEqual(result.error, {"code": failure.code, "retryable": failure.retryable})


class HttpTransportTests(unittest.TestCase):
    def _request(self, *, max_bytes: int = 64, headers: tuple[tuple[str, str], ...] = ()) -> JsonRequest:
        return JsonRequest(
            method="GET",
            url="https://example.test/public-profile",
            timeout_seconds=2.5,
            max_bytes=max_bytes,
            headers=headers,
        )

    def test_request_json_reads_once_with_bounded_public_headers(self) -> None:
        response = FakeResponse(b'{"ok":true}', {"Content-Length": "11"})
        opener = FakeOpener(response)

        payload = request_json(self._request(), opener=opener)

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(len(opener.calls), 1)
        upstream_request, timeout = opener.calls[0]
        self.assertEqual(timeout, 2.5)
        headers = {name.lower(): value for name, value in upstream_request.header_items()}
        self.assertEqual(headers["accept"], "application/json")
        self.assertIn("user-agent", headers)
        self.assertNotIn("authorization", headers)
        self.assertNotIn("cookie", headers)
        self.assertEqual(response.read_calls, 1)

    def test_oversized_and_invalid_json_responses_are_malformed(self) -> None:
        cases = (
            (FakeResponse(b"{}", {"Content-Length": "65"}), "response_too_large"),
            (FakeResponse(b"x" * 65), "response_too_large"),
            (FakeResponse(b"not-json"), "invalid_json"),
            (FakeResponse(b"\xff"), "invalid_json"),
        )
        for response, code in cases:
            with self.subTest(code=code, body_length=len(response._body)):
                opener = FakeOpener(response)
                with self.assertRaises(SourceFailure) as raised:
                    request_json(self._request(), opener=opener)
                self.assertEqual(raised.exception.state, "malformed_response")
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(len(opener.calls), 1)

    def test_http_network_and_timeout_failures_are_classified_without_retry(self) -> None:
        cases = (
            (
                HTTPError("https://example.test", 404, "not found", {}, None),
                "unavailable",
                "profile_not_found",
                False,
            ),
            (
                HTTPError(
                    "https://example.test",
                    403,
                    "rate limited",
                    {"x-ratelimit-remaining": "0"},
                    None,
                ),
                "upstream_error",
                "rate_limited",
                True,
            ),
            (
                HTTPError("https://example.test", 429, "rate limited", {}, None),
                "upstream_error",
                "rate_limited",
                True,
            ),
            (
                HTTPError("https://example.test", 400, "bad request", {}, None),
                "upstream_error",
                "http_4xx",
                False,
            ),
            (
                HTTPError("https://example.test", 500, "server error", {}, None),
                "upstream_error",
                "http_5xx",
                True,
            ),
            (
                HTTPError("https://example.test", 302, "redirect", {}, None),
                "upstream_error",
                "redirect_rejected",
                False,
            ),
            (socket.timeout(), "timeout", "request_timeout", True),
            (URLError(socket.timeout()), "timeout", "request_timeout", True),
            (URLError("offline"), "upstream_error", "network_error", True),
            (OSError("offline"), "upstream_error", "network_error", True),
        )
        for upstream_error, state, code, retryable in cases:
            with self.subTest(code=code, upstream_type=type(upstream_error).__name__):
                opener = FakeOpener(upstream_error)
                with self.assertRaises(SourceFailure) as raised:
                    request_json(self._request(), opener=opener)
                self.assertEqual(raised.exception.state, state)
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(raised.exception.retryable, retryable)
                self.assertEqual(len(opener.calls), 1)

    def test_credential_headers_are_rejected_before_network(self) -> None:
        for header in ("Authorization", "authorization", "Cookie", "cookie"):
            with self.subTest(header=header):
                opener = FakeOpener(FakeResponse(b"{}"))
                with self.assertRaisesRegex(ValueError, "Credential headers"):
                    request_json(
                        self._request(headers=((header, "not-a-real-credential"),)),
                        opener=opener,
                    )
                self.assertEqual(opener.calls, [])


class FixtureContractTests(unittest.TestCase):
    def test_offline_fixture_is_deterministic_complete_and_unverified(self) -> None:
        first = offline_fixture_tags("demo_001")
        second = offline_fixture_tags("demo_001")
        other_user = offline_fixture_tags("demo_other")

        self.assertEqual(first, second)
        self.assertNotEqual(first, other_user)
        self.assertEqual(len(first), 21)
        self.assertEqual(len({tag.tag_id for tag in first}), 21)
        self.assertEqual(
            {tag.tag_id for tag in first},
            {
                "learning_languages",
                "learning_streak",
                "learning_total_xp",
                "learning_course_xp",
                "learning_current_course",
                "learning_consistency",
                "learning_active_hours",
                "learning_level",
                "sport_primary",
                "sport_weekly",
                "sport_total",
                "sport_active_hours",
                "sport_intensity",
                "coding_public_repositories",
                "coding_primary_languages",
                "coding_recent_event_types",
                "coding_recent_activity_days",
                "coding_solved_total",
                "coding_solved_by_difficulty",
                "coding_accepted_submissions",
                "coding_public_ranking",
            },
        )
        for tag in first:
            self.assertEqual(tag.data_mode, "fixture")
            self.assertFalse(tag.verified)
            self.assertEqual(tag.identity_assurance, "synthetic_fixture")
            self.assertEqual(tag.visibility, "self_only")
            self.assertIsNone(tag.observed_at)

    def test_registry_keeps_live_fixture_and_unavailable_modes_explicit(self) -> None:
        registry = get_source_registry(transport=FailIfCalledTransport(), clock=lambda: FIXED_TIME)

        self.assertEqual(
            {source for source, definition in registry.items() if definition.data_mode == "public_live"},
            {"duolingo", "github", "leetcode_com"},
        )
        self.assertEqual(registry["keep"].data_mode, "fixture")
        self.assertEqual(registry["keep"].identity_assurance, "synthetic_fixture")
        for source in ("netease", "weread", "steam", "github_graphql", "leetcode_cn"):
            with self.subTest(source=source):
                self.assertEqual(registry[source].data_mode, "unavailable")
                self.assertFalse(registry[source].enabled)
                self.assertIsNone(registry[source].adapter)
                self.assertTrue(registry[source].unavailable_reason)


class PersistenceAndRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        config = type(
            "DataSourceTestConfig",
            (Config,),
            {
                "TESTING": True,
                "DATABASE": str(Path(self.temp_dir.name) / "test.sqlite3"),
                "SECRET_KEY": "test",
                "DEMO_MODE": True,
                "DATA_SOURCE_TIMEOUT_SECONDS": 1.0,
            },
        )
        self.app = create_app(config)
        self.client = self.app.test_client()
        self.assertEqual(self.client.post("/demo/login").status_code, 302)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_seeded_offline_account_has_complete_fixture_snapshot_and_no_secret(self) -> None:
        with self.app.app_context():
            db = get_db()
            tags = db.execute(
                """SELECT tag_id, data_mode, verified, identity_assurance, visibility,
                          mapping_version
                   FROM tags WHERE user_id = 'demo_001' ORDER BY tag_id"""
            ).fetchall()
            connections = db.execute(
                """SELECT source, data_mode, access_token, external_subject,
                          identity_assurance, last_state, mapping_version
                   FROM external_connections WHERE user_id = 'demo_001' ORDER BY source"""
            ).fetchall()

        self.assertEqual(len(tags), 21)
        self.assertEqual(len({row["tag_id"] for row in tags}), 21)
        self.assertTrue(all(row["data_mode"] == "fixture" for row in tags))
        self.assertTrue(all(row["verified"] == 0 for row in tags))
        self.assertTrue(all(row["identity_assurance"] == "synthetic_fixture" for row in tags))
        self.assertTrue(all(row["visibility"] == "self_only" for row in tags))
        self.assertTrue(all(row["mapping_version"] == "offline-fixture-v1" for row in tags))
        self.assertEqual([row["source"] for row in connections], ["duolingo", "github", "keep", "leetcode_com"])
        self.assertTrue(all(row["data_mode"] == "fixture" for row in connections))
        self.assertTrue(all(row["access_token"] is None for row in connections))
        self.assertTrue(all(row["external_subject"] is None for row in connections))
        self.assertTrue(all(row["last_state"] == "ready" for row in connections))

    def test_public_duolingo_and_github_successes_persist_only_normalized_tags(self) -> None:
        duolingo_registry = get_source_registry(
            transport=QueueTransport(load_fixture("duolingo_profile.json")),
            clock=lambda: FIXED_TIME,
        )
        github_registry = get_source_registry(
            transport=QueueTransport(
                load_fixture("github_user.json"),
                load_fixture("github_repositories.json"),
                load_fixture("github_events.json"),
            ),
            clock=lambda: FIXED_TIME,
        )
        with self.app.app_context():
            duolingo_result = sync_source(
                "demo_001", "duolingo", "duo", registry=duolingo_registry
            )
            github_result = sync_source(
                "demo_001", "github", "octocat", registry=github_registry
            )
            db = get_db()
            rows = db.execute(
                """SELECT tag_id, source, verified, visibility, data_mode,
                          identity_assurance, mapping_version
                   FROM tags
                   WHERE user_id = 'demo_001' AND source IN ('duolingo', 'github')
                   ORDER BY source, tag_id"""
            ).fetchall()
            connections = db.execute(
                """SELECT source, access_token, external_subject, refreshed_at,
                          data_mode, identity_assurance, last_state, last_error_code
                   FROM external_connections
                   WHERE user_id = 'demo_001' AND source IN ('duolingo', 'github')
                   ORDER BY source"""
            ).fetchall()
            database_dump = "\n".join(db.iterdump())

        self.assertEqual((duolingo_result.state, github_result.state), ("ready", "ready"))
        self.assertEqual(len(rows), 9)
        self.assertTrue(all(row["verified"] == 1 for row in rows))
        self.assertTrue(all(row["visibility"] == "self_only" for row in rows))
        self.assertTrue(all(row["data_mode"] == "public_live" for row in rows))
        self.assertTrue(all(row["identity_assurance"] == "unverified_public_handle" for row in rows))
        self.assertEqual(
            [(row["source"], row["external_subject"]) for row in connections],
            [("duolingo", "duo"), ("github", "octocat")],
        )
        self.assertTrue(all(row["access_token"] is None for row in connections))
        self.assertTrue(all(row["last_state"] == "ready" for row in connections))
        self.assertNotIn("SHOULD_NOT_PERSIST", database_dump)
        self.assertNotIn("excluded-repository-name", database_dump)
        self.assertNotIn("excluded@example.test", database_dump)

    def test_failed_refresh_preserves_last_success_and_records_bounded_state(self) -> None:
        success_registry = get_source_registry(
            transport=QueueTransport(load_fixture("duolingo_profile.json")),
            clock=lambda: FIXED_TIME,
        )
        timeout_registry = get_source_registry(
            transport=QueueTransport(
                SourceFailure("timeout", "request_timeout", retryable=True)
            ),
            clock=lambda: LATER_TIME,
        )
        with self.app.app_context():
            sync_source("demo_001", "duolingo", "duo", registry=success_registry)
            db = get_db()
            tags_before = [
                tuple(row)
                for row in db.execute(
                    """SELECT tag_id, value_json, verified, data_mode, mapping_version
                       FROM tags WHERE user_id = 'demo_001' AND source = 'duolingo'
                       ORDER BY tag_id"""
                ).fetchall()
            ]
            connection_before = dict(
                db.execute(
                    "SELECT * FROM external_connections WHERE user_id = 'demo_001' AND source = 'duolingo'"
                ).fetchone()
            )

            result = sync_source("demo_001", "duolingo", "duo", registry=timeout_registry)
            tags_after = [
                tuple(row)
                for row in db.execute(
                    """SELECT tag_id, value_json, verified, data_mode, mapping_version
                       FROM tags WHERE user_id = 'demo_001' AND source = 'duolingo'
                       ORDER BY tag_id"""
                ).fetchall()
            ]
            connection_after = dict(
                db.execute(
                    "SELECT * FROM external_connections WHERE user_id = 'demo_001' AND source = 'duolingo'"
                ).fetchone()
            )

        self.assertEqual((result.state, result.error_code), ("timeout", "request_timeout"))
        self.assertEqual(tags_after, tags_before)
        for key in (
            "status",
            "access_token",
            "refreshed_at",
            "data_mode",
            "external_subject",
            "identity_assurance",
            "mapping_version",
        ):
            self.assertEqual(connection_after[key], connection_before[key], key)
        self.assertEqual(connection_after["last_state"], "timeout")
        self.assertEqual(connection_after["last_error_code"], "request_timeout")
        self.assertEqual(connection_after["last_attempted_at"], LATER_TIME)

    def test_success_write_rolls_back_if_one_tag_insert_fails(self) -> None:
        registry = get_source_registry(
            transport=QueueTransport(load_fixture("duolingo_profile.json")),
            clock=lambda: FIXED_TIME,
        )
        with self.app.app_context():
            db = get_db()
            tags_before = [
                tuple(row)
                for row in db.execute(
                    """SELECT tag_id, value_json, verified, data_mode, mapping_version
                       FROM tags WHERE user_id = 'demo_001' AND source = 'duolingo'
                       ORDER BY tag_id"""
                ).fetchall()
            ]
            connection_before = tuple(
                db.execute(
                    """SELECT status, access_token, refreshed_at, data_mode, external_subject,
                              identity_assurance, last_state, last_error_code,
                              last_attempted_at, mapping_version
                       FROM external_connections
                       WHERE user_id = 'demo_001' AND source = 'duolingo'"""
                ).fetchone()
            )
            db.execute(
                """CREATE TRIGGER reject_learning_total_xp
                   BEFORE INSERT ON tags
                   WHEN NEW.tag_id = 'learning_total_xp'
                   BEGIN
                       SELECT RAISE(ABORT, 'forced test failure');
                   END"""
            )
            db.commit()

            with self.assertRaises(sqlite3.IntegrityError):
                sync_source("demo_001", "duolingo", "duo", registry=registry)

            tags_after = [
                tuple(row)
                for row in db.execute(
                    """SELECT tag_id, value_json, verified, data_mode, mapping_version
                       FROM tags WHERE user_id = 'demo_001' AND source = 'duolingo'
                       ORDER BY tag_id"""
                ).fetchall()
            ]
            connection_after = tuple(
                db.execute(
                    """SELECT status, access_token, refreshed_at, data_mode, external_subject,
                              identity_assurance, last_state, last_error_code,
                              last_attempted_at, mapping_version
                       FROM external_connections
                       WHERE user_id = 'demo_001' AND source = 'duolingo'"""
                ).fetchone()
            )

        self.assertEqual(tags_after, tags_before)
        self.assertEqual(connection_after, connection_before)

    def test_connection_page_is_truthful_and_has_no_credential_controls(self) -> None:
        response = self.client.get("/profile/connections")
        html = response.get_data(as_text=True)
        lowered = html.lower()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(html.count("PUBLIC LIVE"), 3)
        self.assertIn("多邻国 Duolingo", html)
        self.assertIn("GitHub", html)
        self.assertIn("LeetCode.com", html)
        self.assertIn("演示数据 Fixture", html)
        self.assertIn("Keep", html)
        for source in ("netease", "weread", "steam", "github_graphql", "leetcode_cn"):
            with self.subTest(source=source):
                self.assertIn(f'data-source="{source}" data-mode="unavailable"', html)
                self.assertNotIn(f'/profile/connections/{source}/sync', html)
        self.assertIn("来自实时公开资料，不代表账号归属已验证", html)
        self.assertIn("用于演示流程，不是账号实况", html)
        self.assertEqual(html.count('name="external_handle"'), 3)
        self.assertNotIn("/authorize", html)
        self.assertNotIn("authorization_code", lowered)
        self.assertNotIn('type="password"', lowered)
        self.assertNotIn('name="token"', lowered)
        self.assertNotIn('name="cookie"', lowered)
        self.assertNotIn('name="authorization"', lowered)

    def test_sync_route_uses_injected_public_transport_and_does_not_leak_handle_to_profile(self) -> None:
        handle = "unique-public-handle"
        registry = get_source_registry(
            transport=QueueTransport(load_fixture("duolingo_profile.json")),
            clock=lambda: FIXED_TIME,
        )
        with patch("app.routes.auth.get_source_registry", return_value=registry):
            response = self.client.post(
                "/profile/connections/duolingo/sync",
                data={
                    "external_handle": handle,
                    "data_mode": "fixture",
                    "verified": "false",
                },
            )

        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            connection = get_db().execute(
                """SELECT data_mode, external_subject, access_token, last_state
                   FROM external_connections
                   WHERE user_id = 'demo_001' AND source = 'duolingo'"""
            ).fetchone()
        self.assertEqual(connection["data_mode"], "public_live")
        self.assertEqual(connection["external_subject"], handle)
        self.assertIsNone(connection["access_token"])
        self.assertEqual(connection["last_state"], "ready")
        profile_html = self.client.get("/profile").get_data(as_text=True)
        self.assertNotIn(handle, profile_html)

    def test_unavailable_and_production_fixture_posts_are_rejected(self) -> None:
        self.assertEqual(
            self.client.post("/profile/connections/netease/sync").status_code,
            404,
        )

        production_dir = tempfile.TemporaryDirectory()
        self.addCleanup(production_dir.cleanup)
        production_config = type(
            "ProductionDataSourceTestConfig",
            (Config,),
            {
                "TESTING": True,
                "DATABASE": str(Path(production_dir.name) / "production.sqlite3"),
                "SECRET_KEY": "test",
                "DEMO_MODE": False,
            },
        )
        production_app = create_app(production_config)
        production_client = production_app.test_client()
        registration = production_client.post(
            "/register",
            data={
                "email": "public-user@example.test",
                "password": "strong-test-password",
                "anonymous_alias": "公开数据用户",
                "birth_year": "1998",
                "gender": "female",
                "match_gender": "any",
                "city": "上海",
                "purposes": ["学习搭子"],
                "interests": ["人工智能"],
                "mbti": "INFP",
                "zodiac": "天秤",
                "schedule": "正常",
            },
        )
        self.assertEqual(registration.status_code, 302)
        html = production_client.get("/profile/connections").get_data(as_text=True)
        self.assertIn("演示模式已关闭，本次运行不载入 Fixture", html)
        self.assertNotIn("/profile/connections/keep/sync", html)
        self.assertEqual(
            production_client.post("/profile/connections/keep/sync").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
