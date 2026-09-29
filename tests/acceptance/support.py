from __future__ import annotations

import os
import re
import socket
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator
from unittest import mock

from app import create_app
from app.config import Config
from app.db import get_db


ROOT = Path(__file__).resolve().parents[2]
FAILURE_CATEGORIES = ("network", "input", "auth", "route", "assertion")
REQUIRED_FIXTURE_KEYS = {
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
}


def acceptance(category: str, control: str):
    """Attach stable reporting metadata to one unittest method."""
    if category not in FAILURE_CATEGORIES:
        raise ValueError(f"unknown acceptance category: {category}")

    def decorate(function):
        function.acceptance_category = category
        function.acceptance_control = control
        return function

    return decorate


class _InputParser(HTMLParser):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "input":
            return
        values = dict(attrs)
        if values.get("name") == self.name and values.get("value") is not None:
            self.values.append(values["value"] or "")


def input_value(html: str, name: str) -> str:
    parser = _InputParser(name)
    parser.feed(html)
    if not parser.values:
        raise AssertionError(f"input {name!r} was not found")
    return parser.values[0]


@contextmanager
def simulated_network_failure(
    message: str = "qa-offline-network",
    *,
    timeout: bool = False,
) -> Iterator[mock.Mock]:
    """Fail standard-library outbound connections without opening a socket."""
    failure = TimeoutError(message) if timeout else OSError(message)
    with mock.patch.object(socket, "create_connection", side_effect=failure) as guarded:
        yield guarded


class AcceptanceCase(unittest.TestCase):
    """Create a fresh Flask application and disposable SQLite database per case."""

    maxDiff = None

    def setUp(self) -> None:
        parent_text = os.environ.get("REALTAGS_ACCEPTANCE_TMPDIR")
        parent = Path(parent_text).resolve() if parent_text else None
        if parent is not None:
            parent.mkdir(parents=True, exist_ok=True)
        self._temp_dir = tempfile.TemporaryDirectory(
            prefix="case-",
            dir=str(parent) if parent is not None else None,
        )
        self.addCleanup(self._temp_dir.cleanup)
        self._network_guard = mock.patch.object(
            socket,
            "create_connection",
            side_effect=OSError("external network disabled by acceptance case"),
        )
        self._network_guard.start()
        self.addCleanup(self._network_guard.stop)
        self.case_root = Path(self._temp_dir.name).resolve()
        self.database = self.case_root / "acceptance.sqlite3"
        self.app = self.make_app("acceptance.sqlite3", demo_mode=True)
        self.client = self.app.test_client()

        instance_database = (ROOT / "instance" / "realtags.sqlite3").resolve()
        self.assertNotEqual(self.database.resolve(), instance_database)
        self.assertEqual(self.database.resolve().parent, self.case_root)
        if parent is not None:
            self.assertTrue(self.case_root.is_relative_to(parent))

    def make_app(self, database_name: str, *, demo_mode: bool):
        database = self.case_root / database_name
        config = type(
            f"AcceptanceConfig_{database_name.replace('.', '_')}",
            (Config,),
            {
                "TESTING": True,
                "DATABASE": str(database),
                "SECRET_KEY": "qa-acceptance-only",
                "DEMO_MODE": demo_mode,
            },
        )
        return create_app(config)

    def login_demo(self, client=None):
        actor = client or self.client
        response = actor.post("/demo/login")
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        return actor

    def register_user(
        self,
        *,
        app=None,
        email: str = "acceptance-user@example.test",
        alias: str = "验收旅人",
    ):
        target_app = app or self.app
        client = target_app.test_client()
        response = client.post(
            "/register",
            data={
                "email": email,
                "password": "acceptance-password",
                "anonymous_alias": alias,
                "birth_year": "1998",
                "gender": "male",
                "match_gender": "male",
                "city": "北京",
                "purposes": ["随便聊聊"],
                "interests": ["阅读", "游戏"],
                "mbti": "",
                "zodiac": "",
                "schedule": "",
            },
        )
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        with client.session_transaction() as flask_session:
            user_id = flask_session["user_id"]
        return client, user_id

    def complete_match_to_result(self, client=None) -> tuple[str, str, str]:
        actor = client or self.client
        started = actor.post("/matches/search/start")
        self.assertEqual(started.status_code, 302, started.get_data(as_text=True))
        searching = actor.get(started.headers["Location"])
        self.assertEqual(searching.status_code, 200, searching.get_data(as_text=True))
        searching_html = searching.get_data(as_text=True)
        attempt_id = input_value(searching_html, "attempt_id")
        completed = actor.post("/matches/search/complete", data={"attempt_id": attempt_id})
        self.assertEqual(completed.status_code, 302, completed.get_data(as_text=True))
        result_path = completed.headers["Location"]
        candidate_id = result_path.rstrip("/").rsplit("/", 1)[-1]
        result = actor.get(result_path)
        self.assertEqual(result.status_code, 200, result.get_data(as_text=True))
        return candidate_id, attempt_id, result.get_data(as_text=True)

    def event_form(self, **overrides: str | list[str]) -> dict[str, str | list[str]]:
        local_now = datetime.now(timezone(timedelta(hours=8)))
        start = (local_now + timedelta(days=14)).replace(hour=19, minute=0, second=0, microsecond=0)
        form: dict[str, str | list[str]] = {
            "title": "Acceptance boundary event",
            "description": "Acceptance-only event.",
            "poi_id": "poi_001",
            "start_at": start.strftime("%Y-%m-%dT%H:%M"),
            "signup_deadline": (start - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
            "min_size": "3",
            "max_size": "5",
            "budget_level": "50-100",
            "pay_type": "AA",
            "required_tags": ["interest_ai"],
            "gender_policy": "any",
            "signup_mode": "review",
        }
        form.update(overrides)
        return form

    def table_columns(self, table: str) -> set[str]:
        with self.app.app_context():
            return {row["name"] for row in get_db().execute(f"PRAGMA table_info({table})").fetchall()}

    def route_exists(self, route: str) -> bool:
        return any(rule.rule == route for rule in self.app.url_map.iter_rules())

    def datasource_contract_is_assembled(self) -> bool:
        connection_columns = self.table_columns("external_connections")
        tag_columns = self.table_columns("tags")
        return (
            self.route_exists("/profile/connections/<source>/sync")
            and {
                "data_mode",
                "external_subject",
                "identity_assurance",
                "last_state",
                "last_error_code",
                "last_attempted_at",
                "mapping_version",
            }
            <= connection_columns
            and {"data_mode", "evidence_kind", "identity_assurance", "mapping_version"}
            <= tag_columns
        )

    def require_datasource_contract(self) -> None:
        if self.datasource_contract_is_assembled():
            return
        reason = "assembly pending: target sync route and provenance schema are not both present"
        if os.environ.get("REALTAGS_ACCEPTANCE_REQUIRE_ASSEMBLY") == "1":
            self.fail(reason)
        self.skipTest(reason)

    def require_core_contract(self) -> None:
        if (ROOT / "tests" / "test_core_contracts.py").is_file():
            return
        reason = "assembly pending: CORE-001 contract tests are not present"
        if os.environ.get("REALTAGS_ACCEPTANCE_REQUIRE_ASSEMBLY") == "1":
            self.fail(reason)
        self.skipTest(reason)

    def row_count(self, table: str, where: str = "", params: tuple = ()) -> int:
        query = f"SELECT COUNT(*) AS count FROM {table}"
        if where:
            query += f" WHERE {where}"
        with self.app.app_context():
            return get_db().execute(query, params).fetchone()["count"]

    def source_tags(self, user_id: str, source: str) -> list[tuple]:
        stable_columns = [
            "tag_id",
            "category",
            "name",
            "value_json",
            "source",
            "verified",
            "visibility",
            "data_mode",
            "evidence_kind",
            "identity_assurance",
            "mapping_version",
        ]
        available = self.table_columns("tags")
        selected = [column for column in stable_columns if column in available]
        with self.app.app_context():
            rows = get_db().execute(
                f"SELECT {', '.join(selected)} FROM tags WHERE user_id = ? AND source = ? ORDER BY tag_id, id",
                (user_id, source),
            ).fetchall()
        return [tuple(row[column] for column in selected) for row in rows]

    def source_connection(self, user_id: str, source: str) -> dict | None:
        available = self.table_columns("external_connections")
        selected = [
            column
            for column in (
                "source",
                "status",
                "refreshed_at",
                "data_mode",
                "external_subject",
                "identity_assurance",
                "last_state",
                "last_error_code",
                "last_attempted_at",
                "mapping_version",
            )
            if column in available
        ]
        with self.app.app_context():
            row = get_db().execute(
                f"SELECT {', '.join(selected)} FROM external_connections WHERE user_id = ? AND source = ?",
                (user_id, source),
            ).fetchone()
        return dict(row) if row else None

    def assert_contains_smoothed_score(self, html: str) -> None:
        scores = [int(value) for value in re.findall(r"(?<!\d)(\d{2})%", html)]
        self.assertTrue(any(60 <= score <= 98 for score in scores), html)
