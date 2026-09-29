from __future__ import annotations

from app.db import get_db

try:
    from .support import (
        REQUIRED_FIXTURE_KEYS,
        AcceptanceCase,
        acceptance,
        simulated_network_failure,
    )
except ImportError:  # Direct discovery with tests/acceptance as the start directory.
    from support import (
        REQUIRED_FIXTURE_KEYS,
        AcceptanceCase,
        acceptance,
        simulated_network_failure,
    )


class DatasourceBoundaryAcceptanceTests(AcceptanceCase):
    @acceptance("auth", "AUTH-02")
    def test_public_sync_requires_login_and_has_no_side_effect(self) -> None:
        self.require_datasource_contract()
        before_tags = self.row_count("tags")
        before_connections = self.row_count("external_connections")
        response = self.client.post(
            "/profile/connections/github/sync",
            data={"external_handle": "offlinecandidate"},
        )
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        self.assertTrue(response.headers["Location"].endswith("/login"))
        self.assertEqual(self.row_count("tags"), before_tags)
        self.assertEqual(self.row_count("external_connections"), before_connections)

    @acceptance("auth", "STATE-10")
    def test_connection_surface_removes_fake_authorization_and_secret_inputs(self) -> None:
        self.require_datasource_contract()
        self.login_demo()
        html = self.client.get("/profile/connections").get_data(as_text=True)
        for forbidden in (
            "authorization_code",
            "demo-authorized",
            'type="password"',
            'name="token"',
            'name="cookie"',
        ):
            self.assertNotIn(forbidden, html)
        self.assertIn("公开数据", html)
        self.assertIn("Fixture", html)
        self.assertIn("本次演示不可用", html)
        self.assertEqual(
            self.client.post(
                "/profile/connections/duolingo/authorize",
                data={"authorization_code": "demo-authorized"},
            ).status_code,
            404,
        )

    @acceptance("route", "STATE-03")
    def test_unavailable_source_has_no_active_route_or_side_effect(self) -> None:
        self.require_datasource_contract()
        self.login_demo()
        before_tags = self.row_count("tags")
        before_connections = self.row_count("external_connections")
        response = self.client.post("/profile/connections/netease/sync")
        self.assertEqual(response.status_code, 404, response.get_data(as_text=True))
        self.assertEqual(self.row_count("tags"), before_tags)
        self.assertEqual(self.row_count("external_connections"), before_connections)

    @acceptance("input", "STATE-05")
    def test_invalid_public_handle_returns_before_transport_and_preserves_tags(self) -> None:
        self.require_datasource_contract()
        self.login_demo()
        before = self.source_tags("demo_001", "github")
        with simulated_network_failure() as network:
            for handle in ("", "https://example.invalid/profile", "bad handle"):
                with self.subTest(handle=handle):
                    response = self.client.post(
                        "/profile/connections/github/sync",
                        data={"external_handle": handle},
                    )
                    self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        network.assert_not_called()
        self.assertEqual(self.source_tags("demo_001", "github"), before)
        connection = self.source_connection("demo_001", "github")
        self.assertEqual(connection["last_state"], "invalid_input")
        self.assertIn(connection["last_error_code"], {"missing_handle", "invalid_handle"})

    @acceptance("network", "STATE-07")
    def test_public_live_network_failure_preserves_last_success_without_fixture_fallback(self) -> None:
        self.require_datasource_contract()
        self.login_demo()
        before_tags = self.source_tags("demo_001", "github")
        before_connection = self.source_connection("demo_001", "github")

        with simulated_network_failure("qa-network-sentinel") as network:
            response = self.client.post(
                "/profile/connections/github/sync",
                data={"external_handle": "offlinecandidate"},
            )
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        self.assertGreater(network.call_count, 0)
        self.assertEqual(self.source_tags("demo_001", "github"), before_tags)

        after_connection = self.source_connection("demo_001", "github")
        self.assertEqual(after_connection["last_state"], "upstream_error")
        self.assertEqual(after_connection["last_error_code"], "network_error")
        if before_connection:
            self.assertEqual(after_connection["refreshed_at"], before_connection["refreshed_at"])
            self.assertEqual(after_connection["data_mode"], before_connection["data_mode"])

        rendered = self.client.get("/profile/connections").get_data(as_text=True)
        self.assertNotIn("qa-network-sentinel", rendered)
        with self.app.app_context():
            values = [
                str(value)
                for row in get_db().execute(
                    "SELECT * FROM external_connections WHERE user_id = ? AND source = ?",
                    ("demo_001", "github"),
                ).fetchall()
                for value in tuple(row)
            ]
        self.assertNotIn("qa-network-sentinel", "\n".join(values))

    @acceptance("network", "STATE-04")
    def test_public_live_timeout_is_retryable_and_preserves_last_success(self) -> None:
        self.require_datasource_contract()
        self.login_demo()
        before_tags = self.source_tags("demo_001", "duolingo")
        before_connection = self.source_connection("demo_001", "duolingo")

        with simulated_network_failure("qa-timeout-sentinel", timeout=True) as network:
            response = self.client.post(
                "/profile/connections/duolingo/sync",
                data={"external_handle": "offlinecandidate"},
            )
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        self.assertGreater(network.call_count, 0)
        self.assertEqual(self.source_tags("demo_001", "duolingo"), before_tags)

        after_connection = self.source_connection("demo_001", "duolingo")
        self.assertEqual(after_connection["last_state"], "timeout")
        self.assertEqual(after_connection["last_error_code"], "request_timeout")
        if before_connection:
            self.assertEqual(after_connection["refreshed_at"], before_connection["refreshed_at"])
            self.assertEqual(after_connection["data_mode"], before_connection["data_mode"])
        rendered = self.client.get("/profile/connections").get_data(as_text=True)
        self.assertNotIn("qa-timeout-sentinel", rendered)

    @acceptance("assertion", "STATE-02/P0-07")
    def test_offline_fixture_snapshot_is_truthful_and_complete(self) -> None:
        self.require_datasource_contract()
        self.login_demo()
        with self.app.app_context():
            rows = get_db().execute(
                """SELECT tag_id, verified, visibility, data_mode, identity_assurance
                   FROM tags WHERE user_id = ? AND data_mode = 'fixture' ORDER BY tag_id""",
                ("demo_001",),
            ).fetchall()
        keys = [row["tag_id"] for row in rows]
        self.assertTrue(REQUIRED_FIXTURE_KEYS <= set(keys))
        for key in REQUIRED_FIXTURE_KEYS:
            self.assertEqual(keys.count(key), 1, key)
        self.assertTrue(all(row["verified"] == 0 for row in rows))
        self.assertTrue(all(row["visibility"] == "self_only" for row in rows))
        self.assertTrue(all(row["data_mode"] == "fixture" for row in rows))
        self.assertTrue(all(row["identity_assurance"] == "synthetic_fixture" for row in rows))

        profile = self.client.get("/profile").get_data(as_text=True)
        self.assertIn("演示数据 Fixture", profile)
        self.assertIn("用于演示流程，不是账号实况", profile)

    @acceptance("assertion", "STATE-02/DS-012")
    def test_fixture_reload_is_deterministic_and_production_rejects_it(self) -> None:
        self.require_datasource_contract()
        self.login_demo()
        with simulated_network_failure() as network:
            first = self.client.post("/profile/connections/keep/sync")
            self.assertEqual(first.status_code, 302, first.get_data(as_text=True))
            first_tags = self.source_tags("demo_001", "keep")
            second = self.client.post("/profile/connections/keep/sync")
            self.assertEqual(second.status_code, 302, second.get_data(as_text=True))
            second_tags = self.source_tags("demo_001", "keep")
        network.assert_not_called()
        self.assertEqual(first_tags, second_tags)
        self.assertTrue(first_tags)

        production_app = self.make_app("production.sqlite3", demo_mode=False)
        production_client, user_id = self.register_user(
            app=production_app,
            email="production-user@example.test",
            alias="生产边界用户",
        )
        response = production_client.post("/profile/connections/keep/sync")
        self.assertIn(response.status_code, {302, 404})
        with production_app.app_context():
            fixture_tag_count = get_db().execute(
                "SELECT COUNT(*) AS count FROM tags WHERE user_id = ? AND data_mode = 'fixture'",
                (user_id,),
            ).fetchone()["count"]
            ready_fixture_count = get_db().execute(
                """SELECT COUNT(*) AS count FROM external_connections
                   WHERE user_id = ? AND source = 'keep'
                     AND data_mode = 'fixture' AND last_state = 'ready'""",
                (user_id,),
            ).fetchone()["count"]
        self.assertEqual(fixture_tag_count, 0)
        self.assertEqual(ready_fixture_count, 0)


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
