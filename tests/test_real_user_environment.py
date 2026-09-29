from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import check_password_hash

from app import create_app
from app.config import Config
from app.db import get_db
from run_real_user_test import create_real_user_test_app


class RealUserEnvironmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "real-user-test.sqlite3"
        self.app = create_real_user_test_app(self.database)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _registration_form() -> dict[str, str | list[str]]:
        return {
            "email": "Real.Person@Example.Test",
            "password": "strong-real-user-password",
            "anonymous_alias": "真实旅人",
            "birth_year": "1996",
            "gender": "female",
            "match_gender": "any",
            "city": "上海",
            "purposes": ["学习搭子", "随便聊聊"],
            "interests": ["人工智能", "阅读"],
            "mbti": "INTJ",
            "zodiac": "天秤",
            "schedule": "夜猫子",
        }

    def test_fresh_database_is_empty_and_demo_routes_are_disabled(self) -> None:
        self.assertEqual(Path(self.app.config["DATABASE"]), self.database.resolve())
        self.assertFalse(self.app.config["DEMO_MODE"])
        self.assertFalse(self.app.debug)
        self.assertFalse(self.app.config["SESSION_COOKIE_SECURE"])

        tables = (
            "users",
            "external_connections",
            "tags",
            "events",
            "event_members",
            "conversations",
            "conversation_members",
            "messages",
            "event_coupons",
            "admins",
            "reports",
            "event_reviews",
            "admin_audit_logs",
            "blocks",
        )
        with self.app.app_context():
            counts = {
                table: get_db().execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
                for table in tables
            }
        self.assertEqual(counts, {table: 0 for table in tables})

        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertNotIn("进入预置演示账号", home.get_data(as_text=True))
        self.assertNotIn("Fixture", home.get_data(as_text=True))
        registration = self.client.get("/register")
        registration_html = registration.get_data(as_text=True)
        self.assertEqual(registration.status_code, 200)
        self.assertIn("data-registration-draft", registration_html)
        self.assertIn("刷新或回退会恢复本标签页暂存的资料；密码不会保存", registration_html)
        self.assertIn('/static/js/registration-draft.js', registration_html)
        self.assertEqual(self.client.post("/demo/login").status_code, 404)

    def test_registration_persists_all_fields_and_authenticates_the_session(self) -> None:
        response = self.client.post("/register", data=self._registration_form())

        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        self.assertEqual(response.headers["Location"], "/profile/connections")
        with self.client.session_transaction() as session:
            user_id = session["user_id"]

        with self.app.app_context():
            row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["email"], "real.person@example.test")
            self.assertEqual(row["anonymous_alias"], "真实旅人")
            self.assertEqual(row["birth_year"], 1996)
            self.assertEqual(row["gender"], "female")
            self.assertEqual(row["match_gender"], "any")
            self.assertEqual(row["city"], "上海")
            self.assertEqual(json.loads(row["purposes_json"]), ["学习搭子", "随便聊聊"])
            self.assertEqual(json.loads(row["interests_json"]), ["人工智能", "阅读"])
            self.assertEqual(row["mbti"], "INTJ")
            self.assertEqual(row["zodiac"], "天秤")
            self.assertEqual(row["schedule"], "夜猫子")
            self.assertEqual(row["phone_verified"], 0)
            self.assertEqual(row["is_demo"], 0)
            self.assertNotEqual(row["password_hash"], "strong-real-user-password")
            self.assertTrue(check_password_hash(row["password_hash"], "strong-real-user-password"))
            self.assertEqual(get_db().execute("SELECT COUNT(*) AS count FROM tags").fetchone()["count"], 0)
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) AS count FROM external_connections").fetchone()["count"],
                0,
            )

        connections = self.client.get(response.headers["Location"])
        connections_html = connections.get_data(as_text=True)
        self.assertEqual(connections.status_code, 200)
        self.assertIn("注册成功，已自动登录", connections_html)
        self.assertNotIn("/profile/connections/keep/sync", connections_html)
        self.assertEqual(self.client.post("/profile/connections/keep/sync").status_code, 404)

        profile = self.client.get("/profile").get_data(as_text=True)
        self.assertIn("Public Live 或 unavailable", profile)
        self.assertNotIn("Public Live、Fixture 或 unavailable", profile)

        for path in ("/profile", "/matches", "/conversations"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

        events_page = self.client.get("/events")
        events_html = events_page.get_data(as_text=True)
        self.assertEqual(events_page.status_code, 200)
        self.assertIn("发起需手机号验证", events_html)
        self.assertNotIn('href="/events/new"', events_html)

        rejected_event = self.client.post("/events/new", data={})
        self.assertEqual(rejected_event.status_code, 200)
        self.assertIn("发起线下饭局前需完成手机号验证", rejected_event.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) AS count FROM events").fetchone()["count"], 0)

    def test_startup_rejects_a_demo_database(self) -> None:
        demo_database = Path(self.temp_dir.name) / "demo.sqlite3"
        demo_config = type(
            "DemoContaminationConfig",
            (Config,),
            {
                "DATABASE": str(demo_database),
                "DEMO_MODE": True,
                "SECRET_KEY": "test-only-demo-secret",
                "TESTING": True,
            },
        )
        create_app(demo_config)

        with self.assertRaisesRegex(RuntimeError, "prohibited data"):
            create_real_user_test_app(demo_database)

    def test_real_user_only_mode_rejects_demo_mode_before_seeding(self) -> None:
        database = Path(self.temp_dir.name) / "must-stay-empty.sqlite3"
        unsafe_config = type(
            "UnsafeRealUserConfig",
            (Config,),
            {
                "DATABASE": str(database),
                "DEMO_MODE": True,
                "REAL_USER_ONLY": True,
                "SECRET_KEY": "test-only-secret",
                "TESTING": True,
            },
        )

        with self.assertRaisesRegex(RuntimeError, "cannot run with DEMO_MODE"):
            create_app(unsafe_config)
        self.assertFalse(database.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
