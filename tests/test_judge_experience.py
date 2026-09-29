from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.config import Config
from app.services.chat import start_direct_conversation


class JudgeExperienceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        config = type(
            "JudgeExperienceConfig",
            (Config,),
            {
                "TESTING": True,
                "DATABASE": str(Path(self.temp_dir.name) / "judge-experience.sqlite3"),
                "SECRET_KEY": "judge-experience-test",
                "DEMO_MODE": True,
            },
        )
        self.app = create_app(config)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def login_demo(self) -> None:
        response = self.client.post("/demo/login")
        self.assertEqual(response.status_code, 302)

    def test_guest_home_explains_the_difference_and_has_native_demo_entry(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('data-judge-stage="trust"', html)
        self.assertIn('/static/css/judge-journey.css', html)
        self.assertIn('data-judge-entry', html)
        self.assertRegex(html, r'<form[^>]+method="post"[^>]+action="/demo/login"')
        self.assertIn("3 MINUTE JUDGE PATH", html)
        self.assertIn("进入预置演示账号", html)
        self.assertIn("私密标签 → 匿名匹配 → 破冰解锁 → 餐厅饭局", html)
        self.assertIn("Fixture 会明确标注，不冒充实时授权", html)
        self.assertIn("匹配阶段只展示百分比", html)
        self.assertIn("标签仅本人可见", html)
        self.assertIn("饭局只限公开餐厅", html)
        self.assertNotIn('class="judge-journey"', html)

    def test_signed_in_shell_renders_an_ordered_server_owned_journey(self) -> None:
        self.login_demo()
        pages = {
            "/profile": ("tags", 1),
            "/matches": ("match", 2),
            "/conversations": ("chat", 3),
            "/events": ("event", 4),
        }

        for path, (stage, active_step) in pages.items():
            with self.subTest(path=path):
                html = self.client.get(path).get_data(as_text=True)
                self.assertIn(f'data-judge-stage="{stage}"', html)
                self.assertIn('class="judge-journey"', html)
                offsets = [html.index(f'data-journey-step="{step}"') for step in range(1, 5)]
                self.assertEqual(offsets, sorted(offsets))
                self.assertRegex(
                    html,
                    rf'class="is-active" data-journey-step="{active_step}"[^>]+aria-current="step"',
                )
                for href in ('href="/profile"', 'href="/matches"', 'href="/conversations"', 'href="/events"'):
                    self.assertIn(href, html)
                self.assertNotIn('href="#/', html)

        profile = self.client.get("/profile").get_data(as_text=True)
        self.assertIn("Public Live、Fixture 或 unavailable", profile)
        self.assertIn("下一步：匿名匹配", profile)

    def test_private_profile_labels_fixture_provenance_only_when_rendered(self) -> None:
        self.login_demo()
        fixture_tag = {
            "tag_id": "fixture-provenance-sentinel",
            "category": "学习",
            "name": "Fixture provenance sentinel",
            "value": {"days": 7},
            "source": "duolingo",
            "verified": False,
            "visibility": "self_only",
            "data_mode": "fixture",
        }

        with patch("app.routes.auth.profile_tags", return_value=[fixture_tag]):
            response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        boundary_start = html.index('<div class="profile-truth-boundary">')
        boundary = html[boundary_start : html.index("</div>", boundary_start)]
        fixture_badge = '<span class="status-pill status-neutral">演示数据 Fixture</span>'
        fixture_disclaimer = "<p>用于演示流程，不是账号实况</p>"
        self.assertIn("SELF ONLY · 不会公开", boundary)
        self.assertIn(fixture_badge, boundary)
        self.assertIn(fixture_disclaimer, boundary)

        public_live_tag = {**fixture_tag, "data_mode": "public_live"}
        with patch("app.routes.auth.profile_tags", return_value=[public_live_tag]):
            public_live_html = self.client.get("/profile").get_data(as_text=True)
        self.assertNotIn(fixture_badge, public_live_html)
        self.assertNotIn(fixture_disclaimer, public_live_html)

    def test_match_path_remains_percentage_only_and_native_without_javascript(self) -> None:
        self.login_demo()
        idle = self.client.get("/matches").get_data(as_text=True)
        self.assertIn('action="/matches/search/start"', idle)
        self.assertIn('data-primary-action', idle)
        self.assertNotIn("百分比、匿名代号", idle)

        self.assertEqual(self.client.post("/matches/search/start").status_code, 302)
        with self.client.session_transaction() as flask_session:
            flow = dict(flask_session["match_flow"])

        searching = self.client.get("/matches/searching").get_data(as_text=True)
        self.assertIn('data-match-state="searching"', searching)
        self.assertIn('action="/matches/search/complete"', searching)
        self.assertIn("只返回百分比与隐藏共同点数量", searching)
        self.assertNotIn(flow["candidate_id"], searching)
        self.assertNotIn("夜航星", searching)
        self.assertNotIn("raw_score", searching)
        self.assertNotIn("服务端加权排序", searching)

        complete = self.client.post(
            "/matches/search/complete",
            data={"attempt_id": flow["attempt_id"]},
        )
        self.assertEqual(complete.status_code, 302)
        result = self.client.get(complete.headers["Location"]).get_data(as_text=True)
        self.assertIn('data-match-state="result"', result)
        self.assertRegex(result, r'aria-label="匹配度 \d+%"')
        self.assertIn("SIGNAL ONLY", result)
        self.assertIn("NEXT / L0 CHAT TOOLS", result)
        self.assertIn("开启匿名会话 · 进入 L0", result)
        self.assertIn('action="/matches/search/retry"', result)
        self.assertNotIn("夜航星", result)
        self.assertNotIn("raw_score", result)
        self.assertNotIn("匹配权重", result)

    def test_l0_chat_exposes_native_tools_and_truthful_demo_progress(self) -> None:
        self.login_demo()
        with self.app.app_context():
            conversation_id = start_direct_conversation("demo_001", "demo_002")

        path = f"/conversations/{conversation_id}"
        html = self.client.get(path).get_data(as_text=True)
        self.assertIn('data-judge-stage="chat"', html)
        self.assertIn('href="#mission-tools"', html)
        self.assertIn('id="mission-tools" open', html)
        self.assertIn(f'action="{path}/tools/dice"', html)
        self.assertIn(f'action="{path}/tools/task_card"', html)
        self.assertIn(f'action="{path}/tools/unlock"', html)
        self.assertIn(f'action="{path}/demo/advance"', html)
        self.assertIn("FIXTURE DEMO", html)
        self.assertIn("仅加速三分钟演示，不代表自然关系进度", html)
        self.assertIn("先用破冰工具", html)
        self.assertNotIn("INFJ", html)
        self.assertNotIn("上海 ·", html)

        progress = self.client.post(f"{path}/demo/advance")
        self.assertEqual(progress.status_code, 302)
        advanced = self.client.get(path).get_data(as_text=True)
        self.assertIn("L1 初识", advanced)

    def test_restaurant_event_stage_labels_fixture_commercial_evidence(self) -> None:
        self.login_demo()
        plaza = self.client.get("/events").get_data(as_text=True)
        self.assertIn('data-judge-stage="event"', plaza)
        self.assertIn("把同频带到一张餐桌", plaza)
        self.assertIn("公开餐厅", plaza)
        self.assertIn("商家饭局 · Fixture", plaza)
        self.assertIn("发起主题饭局", plaza)

        event_ids = list(dict.fromkeys(re.findall(r'href="/events/([^"/?#]+)"', plaza)))
        self.assertTrue(event_ids)
        fixture_detail = ""
        for event_id in event_ids:
            candidate = self.client.get(f"/events/{event_id}").get_data(as_text=True)
            if "FIXTURE MERCHANT BENEFIT" in candidate:
                fixture_detail = candidate
                break

        self.assertTrue(fixture_detail, "Expected a seeded Fixture merchant event")
        self.assertIn("不代表真实商家合作、支付或 POS 核销", fixture_detail)
        self.assertNotIn("成员姓名", fixture_detail)

    def test_journey_css_covers_focus_mobile_containment_and_reduced_motion(self) -> None:
        response = self.client.get("/static/css/judge-journey.css")
        self.assertEqual(response.status_code, 200)
        css = response.get_data(as_text=True)
        response.close()

        for safeguard in (
            ":focus-visible",
            "max-inline-size: 100%",
            "min-height: 44px",
            "@media (max-width: 899px)",
            "@media (max-width: 359px)",
            "@media (prefers-reduced-motion: reduce)",
            "@media (forced-colors: active)",
        ):
            with self.subTest(safeguard=safeguard):
                self.assertIn(safeguard, css)


if __name__ == "__main__":
    unittest.main()
