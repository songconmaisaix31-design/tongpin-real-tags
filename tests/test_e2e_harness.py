"""HTTP-level harness for the complete PRD MVP workflow.

Each scenario gets a fresh SQLite database and talks to Flask exclusively through
its test client. The only controlled-clock seam is the existing event scheduler,
which lets us verify deadline transitions without waiting for real time.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import create_app
from app.config import Config
from app.db import get_db
from app.services.chat import get_conversation, start_direct_conversation
from app.services.events import get_event, refresh_event_statuses, viewer_coupon
from app.services.matching import ranked_matches
from app.services.users import profile_tags


class MvpWorkflowHarness(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        config = type(
            "HarnessConfig",
            (Config,),
            {
                "TESTING": True,
                "DATABASE": str(Path(self.temp_dir.name) / "harness.sqlite3"),
                "SECRET_KEY": "harness-secret",
                "DEMO_MODE": True,
            },
        )
        self.app = create_app(config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def actor(self, email: str, password: str = "demo-password"):
        client = self.app.test_client()
        response = client.post("/login", data={"email": email, "password": password})
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        return client

    def create_event(self, host, *, title: str, signup_mode: str = "review") -> str:
        local_now = datetime.now(timezone(timedelta(hours=8)))
        start = (local_now + timedelta(days=14)).replace(hour=19, minute=0, second=0, microsecond=0)
        deadline = start - timedelta(hours=2)
        response = host.post(
            "/events/new",
            data={
                "title": title,
                "poi_id": "poi_001",
                "start_at": start.strftime("%Y-%m-%dT%H:%M"),
                "signup_deadline": deadline.strftime("%Y-%m-%dT%H:%M"),
                "min_size": "3",
                "max_size": "5",
                "budget_level": "50-100",
                "pay_type": "AA",
                "required_tags": ["interest_ai", "lang_learning_en"],
                "gender_policy": "balanced",
                "signup_mode": signup_mode,
                "description": "Harness 验证用活动。",
            },
        )
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        return response.headers["Location"].rstrip("/").rsplit("/", 1)[-1]

    def test_registration_source_sync_and_profile_flow(self) -> None:
        """Visitor rejects legacy authorization and loads a self-only explicit Fixture."""
        visitor = self.app.test_client()
        self.assertEqual(visitor.get("/").status_code, 200)
        registration = visitor.post(
            "/register",
            data={
                "email": "harness-user@example.test",
                "password": "strong-test-password",
                "anonymous_alias": "验证旅人",
                "birth_year": "1998",
                "gender": "female",
                "match_gender": "any",
                "city": "上海",
                "purposes": ["学习搭子", "饭搭子"],
                "interests": ["人工智能", "阅读"],
                "mbti": "INFP",
                "zodiac": "天秤",
                "schedule": "夜猫子",
            },
        )
        self.assertEqual(registration.status_code, 302)
        self.assertEqual(registration.headers["Location"], "/profile/connections")
        legacy_authorization = visitor.post(
            "/profile/connections/duolingo/authorize",
            data={"authorization_code": "demo-authorized"},
        )
        self.assertEqual(legacy_authorization.status_code, 404)
        fixture_sync = visitor.post("/profile/connections/keep/sync")
        self.assertEqual(fixture_sync.status_code, 302)
        profile = visitor.get("/profile")
        self.assertEqual(profile.status_code, 200)
        self.assertIn("keep", profile.get_data(as_text=True))
        with self.app.app_context():
            user_id = self._user_id("harness-user@example.test")
            tags = profile_tags(user_id)
            self.assertEqual(ranked_matches(user_id), [])
            self.assertNotIn(
                user_id,
                [item["candidate"]["id"] for item in ranked_matches("demo_001")],
            )
        self.assertEqual(len(tags), 5)
        self.assertTrue(all(tag["source"] == "keep" for tag in tags))
        self.assertTrue(all(tag["data_mode"] == "fixture" for tag in tags))
        self.assertTrue(all(not tag["verified"] for tag in tags))
        self.assertTrue(all(tag["visibility"] == "self_only" for tag in tags))

    def test_anonymous_match_chat_unlock_and_safety_flow(self) -> None:
        """Two users complete the direct-chat journey without L0 profile leakage."""
        first = self.actor("demo@realtags.local")
        second = self.actor("sora@realtags.local")
        home = first.get("/").get_data(as_text=True)
        self.assertIn('href="/matches"', home)
        self.assertIn("开始一次匿名匹配", home)

        idle = first.get("/matches").get_data(as_text=True)
        self.assertIn('data-match-state="idle"', idle)
        self.assertNotIn("夜航星", idle)
        self.assertEqual(first.post("/matches/search/start").status_code, 302)
        with first.session_transaction() as flask_session:
            flow = dict(flask_session["match_flow"])
        self.assertEqual(flow["candidate_id"], "demo_002")

        searching = first.get("/matches/searching").get_data(as_text=True)
        self.assertIn('data-match-state="searching"', searching)
        self.assertIn('aria-busy="true"', searching)
        self.assertNotIn("夜航星", searching)
        self.assertNotIn("87%", searching)
        for step in ("filter", "similarity", "ranking"):
            self.assertIn(f'data-match-step="{step}"', searching)

        complete = first.post("/matches/search/complete", data={"attempt_id": flow["attempt_id"]})
        self.assertEqual(complete.status_code, 302)
        result = first.get(complete.headers["Location"]).get_data(as_text=True)
        self.assertIn('data-match-state="result"', result)
        self.assertIn("隐藏共同点", result)

        match = first.post(
            f"/matches/{flow['candidate_id']}/start",
            data={"attempt_id": flow["attempt_id"]},
        )
        self.assertEqual(match.status_code, 302)
        conversation_id = match.headers["Location"].rsplit("/", 1)[-1]

        l0 = first.get(f"/conversations/{conversation_id}").get_data(as_text=True)
        self.assertIn("夜航星", l0)
        self.assertNotIn("INFJ", l0)
        self.assertNotIn("当前等级", l0)
        self.assertNotIn("上海 ·", l0)

        for number in range(5):
            self.assertEqual(first.post(f"/conversations/{conversation_id}/messages", data={"content": f"甲方消息 {number}"}).status_code, 302)
            self.assertEqual(second.post(f"/conversations/{conversation_id}/messages", data={"content": f"乙方消息 {number}"}).status_code, 302)
        for tool in ("dice", "task_card", "unlock"):
            self.assertEqual(first.post(f"/conversations/{conversation_id}/tools/{tool}").status_code, 302)

        l1 = first.get(f"/conversations/{conversation_id}").get_data(as_text=True)
        self.assertIn("L1 初识", l1)
        self.assertIn("上海", l1)
        for _ in range(3):
            self.assertEqual(first.post(f"/conversations/{conversation_id}/demo/advance").status_code, 302)
        l3 = first.get(f"/conversations/{conversation_id}").get_data(as_text=True)
        self.assertIn("L3 已解锁标签", l3)

        # Five is the deterministic maximum common-point count of the seeded pair.
        for _ in range(4):
            self.assertEqual(first.post(f"/conversations/{conversation_id}/tools/unlock").status_code, 302)
        l4 = first.get(f"/conversations/{conversation_id}").get_data(as_text=True)
        self.assertIn("交换联系方式", l4)

        self.assertEqual(
            first.post(f"/conversations/{conversation_id}/report", data={"reason": "Harness 安全链路验证"}).status_code,
            302,
        )
        self.assertEqual(first.post(f"/conversations/{conversation_id}/block").status_code, 302)
        with self.app.app_context():
            demo_card_count = get_db().execute(
                """SELECT COUNT(*) AS count FROM messages
                   WHERE conversation_id = ? AND json_extract(metadata_json, '$.kind') = 'demo_progress'""",
                (conversation_id,),
            ).fetchone()["count"]
        self.assertEqual(first.post(f"/conversations/{conversation_id}/demo/advance").status_code, 302)
        with self.app.app_context():
            self.assertEqual(
                get_db().execute(
                    """SELECT COUNT(*) AS count FROM messages
                       WHERE conversation_id = ? AND json_extract(metadata_json, '$.kind') = 'demo_progress'""",
                    (conversation_id,),
                ).fetchone()["count"],
                demo_card_count,
            )
        blocked = first.post("/matches/demo_002/start", follow_redirects=True).get_data(as_text=True)
        self.assertIn("失效", blocked)
        with self.app.app_context():
            conversation = get_conversation(conversation_id, "demo_001")
            report_count = self._report_count()
            self.assertNotIn(
                "demo_002",
                [item["candidate"]["id"] for item in ranked_matches("demo_001")],
            )
        self.assertEqual(conversation["progress"]["level"], 4)
        self.assertEqual(report_count, 1)

    def test_user_hosted_event_review_formation_and_group_chat_flow(self) -> None:
        """An admin approves a user event before anonymous signup forms a 3-person group."""
        host = self.actor("demo@realtags.local")
        applicant_one = self.actor("sora@realtags.local")
        applicant_two = self.actor("run@realtags.local")
        event_id = self.create_event(host, title="Harness 用户发起饭局")

        # User-created events are private until a real administrator reviews them.
        self.assertEqual(applicant_one.get(f"/events/{event_id}").status_code, 404)
        admin = self.app.test_client()
        login = admin.post(
            "/admin/login",
            data={"email": "admin@realtags.local", "password": "admin-password"},
        )
        self.assertEqual(login.status_code, 302)
        queue = admin.get("/admin/").get_data(as_text=True)
        self.assertIn("Harness 用户发起饭局", queue)
        approval = admin.post(
            f"/admin/events/{event_id}/review",
            data={"decision": "approve", "rejection_reason": ""},
        )
        self.assertEqual(approval.status_code, 302)

        self.assertEqual(applicant_one.post(f"/events/{event_id}/signup").status_code, 302)
        self.assertEqual(applicant_two.post(f"/events/{event_id}/signup").status_code, 302)

        review_page = host.get(f"/events/{event_id}").get_data(as_text=True)
        self.assertIn("匿名审核报名", review_page)
        self.assertNotIn("夜航星", review_page)
        self.assertNotIn("风中跑者", review_page)
        with self.app.app_context():
            applicants = self._pending_applicants(event_id)
        self.assertEqual(len(applicants), 2)
        for applicant_id in applicants:
            response = host.post(f"/events/{event_id}/review/{applicant_id}/approve")
            self.assertEqual(response.status_code, 302)
        settled = host.post(f"/events/{event_id}/demo/settle", follow_redirects=True).get_data(as_text=True)
        self.assertIn("活动已成团", settled)
        with self.app.app_context():
            event = get_event(event_id, "demo_001")
        self.assertEqual(event["status"], "formed")
        self.assertTrue(event["group_conversation_id"])
        group = host.get(f"/conversations/{event['group_conversation_id']}").get_data(as_text=True)
        self.assertIn("匿名成员", group)
        self.assertNotIn("demo_002", group)
        self.assertEqual(host.post(f"/conversations/{event['group_conversation_id']}/tools/dice").status_code, 302)

    def test_merchant_deadline_coupon_redemption_and_cancellation_flow(self) -> None:
        """The scheduled path forms a merchant event, issues a coupon, redeems it, and cancels an underfilled event."""
        first = self.actor("demo@realtags.local")
        second = self.actor("sora@realtags.local")
        third = self.actor("run@realtags.local")
        for actor in (first, second, third):
            self.assertEqual(actor.post("/events/event_001/signup").status_code, 302)
        with self.app.app_context():
            merchant_event = get_event("event_001", "demo_001")
            refresh_event_statuses(datetime.fromisoformat(merchant_event["signup_deadline"]) + timedelta(minutes=1))
            formed = get_event("event_001", "demo_001")
            coupon = viewer_coupon("event_001", "demo_001")
        self.assertEqual(formed["status"], "formed")
        self.assertTrue(formed["group_conversation_id"])
        self.assertEqual(coupon["status"], "issued")
        self.assertEqual(
            first.post("/events/event_001/redeem", data={"redeem_code": coupon["redeem_code"]}).status_code, 302
        )
        with self.app.app_context():
            redeemed = viewer_coupon("event_001", "demo_001")
            underfilled = get_event("event_003", "demo_001")
            refresh_event_statuses(datetime.fromisoformat(underfilled["signup_deadline"]) + timedelta(minutes=1))
            cancelled = get_event("event_003", "demo_001")
        self.assertEqual(redeemed["status"], "redeemed")
        self.assertEqual(cancelled["status"], "cancelled")

    @staticmethod
    def _user_id(email: str) -> str:
        from app.db import get_db

        return get_db().execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]

    @staticmethod
    def _pending_applicants(event_id: str) -> list[str]:
        from app.db import get_db

        return [
            row["user_id"]
            for row in get_db().execute(
                "SELECT user_id FROM event_members WHERE event_id = ? AND membership_status = 'pending' ORDER BY joined_at",
                (event_id,),
            ).fetchall()
        ]

    @staticmethod
    def _report_count() -> int:
        return get_db().execute("SELECT COUNT(*) AS count FROM reports").fetchone()["count"]


class RegisteredUserMatchChatHarness(unittest.TestCase):
    """Production-mode proof that two newly registered people can match and converse."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        config = type(
            "ProductionMatchHarnessConfig",
            (Config,),
            {
                "TESTING": True,
                "DATABASE": str(Path(self.temp_dir.name) / "registered-users.sqlite3"),
                "SECRET_KEY": "registered-users-secret",
                "DEMO_MODE": False,
            },
        )
        self.app = create_app(config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _register(self, email: str, alias: str):
        client = self.app.test_client()
        response = client.post(
            "/register",
            data={
                "email": email,
                "password": "strong-test-password",
                "anonymous_alias": alias,
                "birth_year": "1998",
                "gender": "male",
                "match_gender": "male",
                "city": "北京",
                "purposes": ["随便聊聊"],
                "interests": ["游戏", "宠物"],
                "mbti": "",
                "zodiac": "",
                "schedule": "",
            },
        )
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        self.assertEqual(response.headers["Location"], "/profile/connections")
        with client.session_transaction() as flask_session:
            user_id = flask_session["user_id"]
        return client, user_id

    def test_registered_users_match_once_and_exchange_persistent_messages(self) -> None:
        guest = self.app.test_client()
        self.assertNotIn("进入预置演示账号", guest.get("/").get_data(as_text=True))
        self.assertEqual(guest.post("/demo/login").status_code, 404)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) AS count FROM admins").fetchone()["count"], 0)
        created_admin = self.app.test_cli_runner().invoke(
            args=[
                "create-admin",
                "--email",
                "real-admin@example.test",
                "--display-name",
                "真实审核员",
                "--password",
                "real-admin-password",
            ]
        )
        self.assertEqual(created_admin.exit_code, 0, created_admin.output)

        first, first_id = self._register("real-one@example.test", "北辰一号")
        second, second_id = self._register("real-two@example.test", "北辰二号")
        with self.app.app_context():
            users = get_db().execute(
                "SELECT id, mbti, zodiac, schedule, is_demo FROM users ORDER BY created_at"
            ).fetchall()
            self.assertEqual([row["id"] for row in users], [first_id, second_id])
            self.assertTrue(all(row["is_demo"] == 0 for row in users))
            self.assertTrue(all(row["mbti"] == "不知道" for row in users))
            self.assertTrue(all(row["zodiac"] == "不知道" for row in users))
            self.assertTrue(all(row["schedule"] == "正常" for row in users))
            self.assertEqual([item["candidate"]["id"] for item in ranked_matches(first_id)], [second_id])
            self.assertEqual([item["candidate"]["id"] for item in ranked_matches(second_id)], [first_id])

        admin = self.app.test_client()
        self.assertEqual(
            admin.post(
                "/admin/login",
                data={"email": "real-admin@example.test", "password": "real-admin-password"},
            ).status_code,
            302,
        )
        account_directory = admin.get("/admin/").get_data(as_text=True)
        self.assertIn("real-one@example.test", account_directory)
        self.assertIn("真实账户", account_directory)

        forged = first.post(
            f"/matches/{second_id}/start",
            data={"attempt_id": "forged-attempt"},
        )
        self.assertEqual(forged.status_code, 302)
        self.assertTrue(forged.headers["Location"].endswith("/matches"))
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) AS count FROM conversations").fetchone()["count"], 0)

        self.assertEqual(first.post("/matches/search/start").status_code, 302)
        with first.session_transaction() as flask_session:
            flow = dict(flask_session["match_flow"])
        self.assertEqual(flow["candidate_id"], second_id)
        complete = first.post(
            "/matches/search/complete",
            data={"attempt_id": flow["attempt_id"]},
        )
        self.assertEqual(complete.status_code, 302)
        result = first.get(complete.headers["Location"]).get_data(as_text=True)
        self.assertIn('name="attempt_id"', result)
        self.assertIn("开启匿名会话", result)

        started = first.post(
            f"/matches/{second_id}/start",
            data={"attempt_id": flow["attempt_id"]},
        )
        self.assertEqual(started.status_code, 302)
        conversation_id = started.headers["Location"].rsplit("/", 1)[-1]
        self.assertIn(conversation_id, second.get("/conversations").get_data(as_text=True))
        self.assertIn("北辰一号", second.get("/conversations").get_data(as_text=True))

        first_message = "甲方真实账户发来的第一条消息"
        second_message = "乙方已经收到，现在回复"
        self.assertEqual(
            first.post(f"/conversations/{conversation_id}/messages", data={"content": first_message}).status_code,
            302,
        )
        self.assertEqual(
            second.post(f"/conversations/{conversation_id}/messages", data={"content": second_message}).status_code,
            302,
        )
        for client in (first, second):
            transcript = client.get(f"/conversations/{conversation_id}").get_data(as_text=True)
            self.assertIn(first_message, transcript)
            self.assertIn(second_message, transcript)

        with self.app.app_context():
            self.assertEqual(start_direct_conversation(second_id, first_id), conversation_id)
            member_ids = {
                row["user_id"]
                for row in get_db().execute(
                    "SELECT user_id FROM conversation_members WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchall()
            }
            self.assertEqual(member_ids, {first_id, second_id})
            self.assertEqual(
                get_db().execute(
                    "SELECT COUNT(*) AS count FROM conversations WHERE type = 'direct'"
                ).fetchone()["count"],
                1,
            )
            self.assertEqual(
                get_db().execute(
                    """SELECT COUNT(*) AS count FROM messages
                       WHERE conversation_id = ? AND json_extract(metadata_json, '$.kind') = 'match_started'""",
                    (conversation_id,),
                ).fetchone()["count"],
                1,
            )

        outsider, _ = self._register("real-three@example.test", "北辰三号")
        outsider.post(
            f"/conversations/{conversation_id}/report",
            data={"reason": "非成员不能写入举报"},
        )
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) AS count FROM reports").fetchone()["count"], 0)

        self.assertEqual(first.post(f"/conversations/{conversation_id}/block").status_code, 302)
        blocked_message = "拉黑后不应落库"
        self.assertEqual(
            second.post(f"/conversations/{conversation_id}/messages", data={"content": blocked_message}).status_code,
            302,
        )
        blocked_page = second.get(f"/conversations/{conversation_id}").get_data(as_text=True)
        self.assertIn("这段会话已停止联系", blocked_page)
        self.assertNotIn('id="composer"', blocked_page)
        with self.app.app_context():
            self.assertIsNone(
                get_db().execute(
                    "SELECT 1 FROM messages WHERE conversation_id = ? AND content = ?",
                    (conversation_id, blocked_message),
                ).fetchone()
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
