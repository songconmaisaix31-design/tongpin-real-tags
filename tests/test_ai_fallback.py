from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

from app import create_app
from app.config import Config
from app.db import get_db
from app.services.ai_fallback import (
    AiFallbackFailure,
    CompletionRequest,
    ai_fallback_available,
    complete_ai_reply,
    request_chat_completion,
)


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body
        self.headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def read(self, amount: int = -1) -> bytes:
        return self.body if amount < 0 else self.body[:amount]


class CapturingOpener:
    def __init__(self, outcome: FakeResponse | BaseException):
        self.outcome = outcome
        self.calls: list[tuple[object, float]] = []

    def open(self, request: object, timeout: float):
        self.calls.append((request, timeout))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class AiFallbackTransportTests(unittest.TestCase):
    def _request(self, **overrides) -> CompletionRequest:
        values = {
            "url": "https://provider.example.test/v1/chat/completions",
            "api_key": "non-secret-test-key",
            "model": "test-chat-model",
            "messages": (("user", "你好"),),
            "timeout_seconds": 3.0,
        }
        values.update(overrides)
        return CompletionRequest(**values)

    def test_request_is_bounded_openai_compatible_and_non_streaming(self) -> None:
        opener = CapturingOpener(
            FakeResponse(
                json.dumps(
                    {"choices": [{"message": {"content": "  我是 AI 候场搭子。今天想聊什么？  "}}]},
                    ensure_ascii=False,
                ).encode("utf-8")
            )
        )

        reply = request_chat_completion(self._request(), opener=opener)

        self.assertEqual(reply, "我是 AI 候场搭子。今天想聊什么？")
        self.assertEqual(len(opener.calls), 1)
        request, timeout = opener.calls[0]
        self.assertEqual(timeout, 3.0)
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.full_url, "https://provider.example.test/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer non-secret-test-key")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "test-chat-model")
        self.assertFalse(body["stream"])
        self.assertEqual(body["max_tokens"], 180)
        self.assertEqual([item["role"] for item in body["messages"]], ["system", "user"])
        self.assertIn("不是真人匹配对象", body["messages"][0]["content"])

    def test_response_and_http_failures_use_bounded_codes(self) -> None:
        cases = (
            (FakeResponse(b"not-json"), "invalid_response"),
            (FakeResponse(b'{"choices":[]}'), "invalid_response"),
            (
                CapturingOpener(HTTPError("https://provider.example.test", 302, "redirect", {}, None)),
                "redirect_rejected",
            ),
            (
                CapturingOpener(HTTPError("https://provider.example.test", 401, "unauthorized", {}, None)),
                "authentication_failed",
            ),
            (
                CapturingOpener(HTTPError("https://provider.example.test", 403, "forbidden", {}, None)),
                "permission_denied",
            ),
            (
                CapturingOpener(HTTPError("https://provider.example.test", 429, "limited", {}, None)),
                "rate_limited",
            ),
        )
        for outcome, expected in cases:
            with self.subTest(expected=expected):
                opener = outcome if isinstance(outcome, CapturingOpener) else CapturingOpener(outcome)
                with self.assertRaises(AiFallbackFailure) as raised:
                    request_chat_completion(self._request(), opener=opener)
                self.assertEqual(raised.exception.code, expected)

    def test_overlong_reply_is_truncated_before_storage_boundary(self) -> None:
        opener = CapturingOpener(
            FakeResponse(
                json.dumps({"choices": [{"message": {"content": "答" * 700}}]}).encode("utf-8")
            )
        )
        reply = request_chat_completion(self._request(), opener=opener)
        self.assertEqual(len(reply), 500)
        self.assertTrue(reply.endswith("…"))

    def test_legacy_conversations_are_migrated_to_human_counterparts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "legacy-conversations.sqlite3"
            db = sqlite3.connect(database)
            db.execute(
                """CREATE TABLE conversations (
                       id TEXT PRIMARY KEY,
                       type TEXT NOT NULL CHECK(type IN ('direct', 'event_group')),
                       event_id TEXT,
                       demo_progress_offset INTEGER NOT NULL DEFAULT 0,
                       created_at TEXT NOT NULL,
                       archived_at TEXT
                   )"""
            )
            db.execute(
                "INSERT INTO conversations (id, type, created_at) VALUES ('legacy_direct', 'direct', '2026-08-23T00:00:00')"
            )
            db.commit()
            db.close()
            config = type(
                "LegacyAiMigrationConfig",
                (Config,),
                {
                    "TESTING": True,
                    "DATABASE": str(database),
                    "SECRET_KEY": "test",
                    "DEMO_MODE": False,
                    "REAL_USER_ONLY": False,
                },
            )

            app = create_app(config)
            with app.app_context():
                columns = {
                    row["name"]
                    for row in get_db().execute("PRAGMA table_info(conversations)").fetchall()
                }
                legacy = get_db().execute(
                    "SELECT counterpart_type FROM conversations WHERE id = 'legacy_direct'"
                ).fetchone()

        self.assertIn("counterpart_type", columns)
        self.assertEqual(legacy["counterpart_type"], "human")

    def test_availability_rejects_incomplete_or_unsafe_configuration(self) -> None:
        for base_url in (
            "http://provider.example.test/v1",
            "https://user:password@provider.example.test/v1",
            "https://provider.example.test/v1?target=other",
            "https://provider.example.test/v1#fragment",
            "",
        ):
            with self.subTest(base_url=base_url):
                config = type(
                    "InvalidAiConfig",
                    (Config,),
                    {
                        "TESTING": True,
                        "DATABASE": ":memory:",
                        "SECRET_KEY": "test",
                        "DEMO_MODE": False,
                        "AI_FALLBACK_ENABLED": True,
                        "AI_FALLBACK_API_KEY": "non-secret-test-key",
                        "AI_FALLBACK_BASE_URL": base_url,
                        "AI_FALLBACK_MODEL": "test-chat-model",
                    },
                )
                app = create_app(config)
                with app.app_context():
                    self.assertFalse(ai_fallback_available())

    def test_vercel_oidc_is_accepted_only_for_the_exact_ai_gateway_endpoint(self) -> None:
        gateway_config = type(
            "VercelGatewayConfig",
            (Config,),
            {
                "TESTING": True,
                "DATABASE": ":memory:",
                "SECRET_KEY": "test",
                "DEMO_MODE": False,
                "AI_FALLBACK_ENABLED": True,
                "AI_FALLBACK_API_KEY": "",
                "AI_FALLBACK_OIDC_TOKEN": "non-secret-test-oidc-token",
                "AI_FALLBACK_BASE_URL": "https://ai-gateway.vercel.sh/v1",
                "AI_FALLBACK_MODEL": "alibaba/qwen3.5-flash",
            },
        )
        app = create_app(gateway_config)
        requests: list[CompletionRequest] = []
        with app.app_context():
            self.assertTrue(ai_fallback_available())
            reply = complete_ai_reply(
                [("user", "你好")],
                transport=lambda request: requests.append(request) or "你好，我是 AI 候场搭子。",
            )

        self.assertEqual(reply, "你好，我是 AI 候场搭子。")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url, "https://ai-gateway.vercel.sh/v1/chat/completions")
        self.assertEqual(requests[0].api_key, "non-secret-test-oidc-token")

        for unsafe_base_url in (
            "https://provider.example.test/v1",
            "https://ai-gateway.vercel.sh.example.test/v1",
            "https://ai-gateway.vercel.sh:443/v1",
        ):
            with self.subTest(base_url=unsafe_base_url):
                rejected_config = type(
                    "RejectedOidcConfig",
                    (gateway_config,),
                    {"AI_FALLBACK_BASE_URL": unsafe_base_url},
                )
                rejected_app = create_app(rejected_config)
                with rejected_app.app_context():
                    self.assertFalse(ai_fallback_available())

    def test_vercel_runtime_oidc_comes_from_the_request_header(self) -> None:
        runtime_config = type(
            "VercelRuntimeGatewayConfig",
            (Config,),
            {
                "TESTING": True,
                "DATABASE": ":memory:",
                "SECRET_KEY": "test",
                "DEMO_MODE": False,
                "AI_FALLBACK_ENABLED": True,
                "AI_FALLBACK_API_KEY": "",
                "AI_FALLBACK_OIDC_TOKEN": "",
                "AI_FALLBACK_BASE_URL": "https://ai-gateway.vercel.sh/v1",
                "AI_FALLBACK_MODEL": "alibaba/qwen3.5-flash",
            },
        )
        app = create_app(runtime_config)
        requests: list[CompletionRequest] = []

        with app.app_context():
            self.assertFalse(ai_fallback_available())
        with app.test_request_context(
            headers={"x-vercel-oidc-token": "non-secret-runtime-oidc-token"}
        ):
            self.assertTrue(ai_fallback_available())
            complete_ai_reply(
                [("user", "你好")],
                transport=lambda request: requests.append(request) or "你好，我是 AI 候场搭子。",
            )

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].api_key, "non-secret-runtime-oidc-token")

    def test_injected_transport_is_still_bounded(self) -> None:
        config = type(
            "BoundedTransportConfig",
            (Config,),
            {
                "TESTING": True,
                "DATABASE": ":memory:",
                "SECRET_KEY": "test",
                "AI_FALLBACK_ENABLED": True,
                "AI_FALLBACK_API_KEY": "non-secret-test-key",
                "AI_FALLBACK_BASE_URL": "https://provider.example.test/v1",
                "AI_FALLBACK_MODEL": "test-chat-model",
            },
        )
        app = create_app(config)
        with app.app_context():
            reply = complete_ai_reply(
                [("user", "hello")],
                transport=lambda _: "答" * 700,
            )
        self.assertEqual(len(reply), 500)
        self.assertTrue(reply.endswith("…"))


class AiFallbackFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.requests: list[CompletionRequest] = []
        config = type(
            "AiFallbackFlowConfig",
            (Config,),
            {
                "TESTING": True,
                "DATABASE": str(Path(self.temp_dir.name) / "ai-fallback.sqlite3"),
                "SECRET_KEY": "test",
                "DEMO_MODE": False,
                "REAL_USER_ONLY": True,
                "AI_FALLBACK_ENABLED": True,
                "AI_FALLBACK_API_KEY": "non-secret-test-key",
                "AI_FALLBACK_BASE_URL": "https://provider.example.test/v1",
                "AI_FALLBACK_MODEL": "test-chat-model",
                "AI_FALLBACK_MAX_REPLIES": 30,
            },
        )
        self.app = create_app(config)
        self.app.config["AI_FALLBACK_TRANSPORT"] = self._transport

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _transport(self, request: CompletionRequest) -> str:
        self.requests.append(request)
        return "我是明确标注的 AI 候场搭子。你今天最想聊什么？"

    def _register(self, email: str, alias: str, *, gender: str = "female"):
        client = self.app.test_client()
        response = client.post(
            "/register",
            data={
                "email": email,
                "password": "strong-test-password",
                "anonymous_alias": alias,
                "birth_year": "1998",
                "gender": gender,
                "match_gender": "any",
                "city": "上海",
                "purposes": ["随便聊聊"],
                "interests": ["阅读", "影视"],
                "mbti": "INFP",
                "zodiac": "天秤",
                "schedule": "正常",
            },
        )
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        with client.session_transaction() as flask_session:
            user_id = flask_session["user_id"]
        return client, user_id

    def _start_fallback(self, client) -> str:
        response = client.post("/matches/search/start")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/conversations/ai_", response.headers["Location"])
        return response.headers["Location"].rsplit("/", 1)[-1]

    def test_empty_human_pool_creates_labeled_single_member_ai_conversation(self) -> None:
        client, user_id = self._register("solo@example.test", "独行读者")
        match_page = client.get("/matches").get_data(as_text=True)
        self.assertIn("AI 候场搭子可以先陪你聊", match_page)
        self.assertIn("AI STANDBY · NOT A REAL PERSON", match_page)

        conversation_id = self._start_fallback(client)
        self.assertEqual(self.requests, [])
        second_start = self._start_fallback(client)
        self.assertEqual(second_start, conversation_id)

        with self.app.app_context():
            db = get_db()
            conversation = db.execute(
                "SELECT counterpart_type FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            members = db.execute(
                "SELECT user_id FROM conversation_members WHERE conversation_id = ?", (conversation_id,)
            ).fetchall()
            starts = db.execute(
                """SELECT COUNT(*) AS count FROM messages
                   WHERE conversation_id = ?
                     AND json_extract(metadata_json, '$.kind') = 'ai_fallback_started'""",
                (conversation_id,),
            ).fetchone()["count"]
        self.assertEqual(conversation["counterpart_type"], "ai")
        self.assertEqual([row["user_id"] for row in members], [user_id])
        self.assertEqual(starts, 1)

        html = client.get(f"/conversations/{conversation_id}").get_data(as_text=True)
        self.assertIn('data-counterpart-type="ai"', html)
        self.assertIn("AI 候场搭子 · 非真人", html)
        self.assertIn("仅发送最近的文字对话", html)
        self.assertNotIn("解锁匹配点", html)
        self.assertNotIn("拉黑对方", html)

    def test_message_makes_one_minimized_request_and_persists_ai_reply(self) -> None:
        client, user_id = self._register("chat@example.test", "隐私读者")
        conversation_id = self._start_fallback(client)
        user_message = "今天有点紧张，想找一个轻松的话题。"

        response = client.post(
            f"/conversations/{conversation_id}/messages",
            data={"content": user_message},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertEqual(request.messages, (("user", user_message),))
        minimized_context = repr(request.messages)
        for private_value in ("chat@example.test", "隐私读者", user_id, "阅读", "影视"):
            self.assertNotIn(private_value, minimized_context)

        with self.app.app_context():
            rows = get_db().execute(
                """SELECT sender_id, content, metadata_json FROM messages
                   WHERE conversation_id = ? AND message_type = 'text' ORDER BY id""",
                (conversation_id,),
            ).fetchall()
            database_dump = "\n".join(get_db().iterdump())
        self.assertEqual(len(rows), 2)
        self.assertEqual((rows[0]["sender_id"], rows[0]["content"]), (user_id, user_message))
        self.assertIsNone(rows[1]["sender_id"])
        self.assertEqual(json.loads(rows[1]["metadata_json"]), {"kind": "ai_reply"})
        self.assertNotIn("non-secret-test-key", database_dump)

        transcript = client.get(f"/conversations/{conversation_id}").get_data(as_text=True)
        self.assertIn(user_message, transcript)
        self.assertIn("我是明确标注的 AI 候场搭子", transcript)

    def test_human_candidate_always_takes_precedence(self) -> None:
        first, _ = self._register("first@example.test", "真人甲")
        self._register("second@example.test", "真人乙", gender="male")

        response = first.post("/matches/search/start")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/matches/searching"))
        self.assertEqual(self.requests, [])
        with self.app.app_context():
            ai_count = get_db().execute(
                "SELECT COUNT(*) AS count FROM conversations WHERE counterpart_type = 'ai'"
            ).fetchone()["count"]
        self.assertEqual(ai_count, 0)

    def test_candidate_disappearing_during_search_falls_back_to_ai(self) -> None:
        first, _ = self._register("race-first@example.test", "竞态真人甲")
        self._register("race-second@example.test", "竞态真人乙", gender="male")

        started = first.post("/matches/search/start")
        self.assertTrue(started.headers["Location"].endswith("/matches/searching"))
        with first.session_transaction() as flask_session:
            flow = dict(flask_session["match_flow"])
        with self.app.app_context():
            get_db().execute("DELETE FROM users WHERE id = ?", (flow["candidate_id"],))
            get_db().commit()

        completed = first.post(
            "/matches/search/complete",
            data={"attempt_id": flow["attempt_id"]},
        )

        self.assertEqual(completed.status_code, 302)
        self.assertIn("/conversations/ai_", completed.headers["Location"])
        self.assertEqual(self.requests, [])

    def test_candidate_disappearing_continues_with_another_human_first(self) -> None:
        first, _ = self._register("replacement-first@example.test", "候选真人甲")
        self._register("replacement-second@example.test", "候选真人乙", gender="male")
        self._register("replacement-third@example.test", "候选真人丙", gender="male")

        first.post("/matches/search/start")
        with first.session_transaction() as flask_session:
            original_flow = dict(flask_session["match_flow"])
        with self.app.app_context():
            get_db().execute("DELETE FROM users WHERE id = ?", (original_flow["candidate_id"],))
            get_db().commit()

        completed = first.post(
            "/matches/search/complete",
            data={"attempt_id": original_flow["attempt_id"]},
        )

        self.assertTrue(completed.headers["Location"].endswith("/matches/searching"))
        with first.session_transaction() as flask_session:
            replacement_flow = dict(flask_session["match_flow"])
        self.assertNotEqual(replacement_flow["candidate_id"], original_flow["candidate_id"])
        self.assertEqual(replacement_flow["phase"], "searching")
        self.assertEqual(self.requests, [])

    def test_provider_failure_preserves_user_message_without_fake_reply(self) -> None:
        client, _ = self._register("failure@example.test", "故障观察者")
        conversation_id = self._start_fallback(client)

        def fail(_: CompletionRequest) -> str:
            raise AiFallbackFailure("timeout")

        self.app.config["AI_FALLBACK_TRANSPORT"] = fail
        with self.assertLogs(self.app.logger.name, level="WARNING") as captured:
            response = client.post(
                f"/conversations/{conversation_id}/messages",
                data={"content": "这条消息应该保留"},
                follow_redirects=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("消息已保存，但 AI 候场搭子暂时没能回复", response.get_data(as_text=True))
        self.assertTrue(any("AI fallback request failed: timeout" in line for line in captured.output))
        self.assertTrue(all("这条消息应该保留" not in line for line in captured.output))
        with self.app.app_context():
            rows = get_db().execute(
                """SELECT sender_id, content FROM messages
                   WHERE conversation_id = ? AND message_type = 'text'""",
                (conversation_id,),
            ).fetchall()
        self.assertEqual([(row["sender_id"] is None, row["content"]) for row in rows], [(False, "这条消息应该保留")])

    def test_reply_cap_rejects_extra_calls_before_writing(self) -> None:
        self.app.config["AI_FALLBACK_MAX_REPLIES"] = 1
        client, _ = self._register("limited@example.test", "限额观察者")
        conversation_id = self._start_fallback(client)
        client.post(f"/conversations/{conversation_id}/messages", data={"content": "第一条"})
        second = client.post(
            f"/conversations/{conversation_id}/messages",
            data={"content": "第二条"},
            follow_redirects=True,
        )
        self.assertIn("已达到回复上限", second.get_data(as_text=True))
        self.assertEqual(len(self.requests), 1)
        with self.app.app_context():
            stored = get_db().execute(
                "SELECT COUNT(*) AS count FROM messages WHERE conversation_id = ? AND message_type = 'text'",
                (conversation_id,),
            ).fetchone()["count"]
        self.assertEqual(stored, 2)

    def test_disabled_configuration_keeps_ai_history_read_only(self) -> None:
        client, _ = self._register("disabled@example.test", "停用观察者")
        conversation_id = self._start_fallback(client)
        self.app.config["AI_FALLBACK_ENABLED"] = False

        html = client.get(f"/conversations/{conversation_id}").get_data(as_text=True)
        self.assertIn("AI 候场服务当前未启用", html)
        self.assertNotIn('id="composer"', html)
        blocked = client.post(
            f"/conversations/{conversation_id}/messages",
            data={"content": "不应写入"},
            follow_redirects=True,
        )
        self.assertIn("暂时只能查看", blocked.get_data(as_text=True))
        self.assertEqual(self.requests, [])

    def test_forged_human_actions_are_rejected_for_ai_conversation(self) -> None:
        client, _ = self._register("guarded@example.test", "边界观察者")
        conversation_id = self._start_fallback(client)

        tool_response = client.post(
            f"/conversations/{conversation_id}/tools/dice",
            follow_redirects=True,
        )
        self.assertIn("不提供真人破冰与解锁工具", tool_response.get_data(as_text=True))
        block_response = client.post(
            f"/conversations/{conversation_id}/block",
            follow_redirects=True,
        )
        self.assertIn("不是真人账户", block_response.get_data(as_text=True))
        with self.app.app_context():
            db = get_db()
            tool_count = db.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE conversation_id = ? AND message_type = 'tool'",
                (conversation_id,),
            ).fetchone()["count"]
            block_count = db.execute("SELECT COUNT(*) AS count FROM blocks").fetchone()["count"]
        self.assertEqual(tool_count, 0)
        self.assertEqual(block_count, 0)

    def test_ai_output_is_html_escaped(self) -> None:
        client, _ = self._register("escaping@example.test", "转义观察者")
        conversation_id = self._start_fallback(client)
        self.app.config["AI_FALLBACK_TRANSPORT"] = lambda _: "<script>alert('unsafe')</script>"

        client.post(f"/conversations/{conversation_id}/messages", data={"content": "测试输出"})
        html = client.get(f"/conversations/{conversation_id}").get_data(as_text=True)

        self.assertIn("&lt;script&gt;alert", html)
        self.assertNotIn("<script>alert", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
