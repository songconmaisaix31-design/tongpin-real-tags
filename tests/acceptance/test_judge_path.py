from __future__ import annotations

try:
    from .support import AcceptanceCase, acceptance, simulated_network_failure
except ImportError:  # Direct discovery with tests/acceptance as the start directory.
    from support import AcceptanceCase, acceptance, simulated_network_failure


class JudgePathAcceptanceTests(AcceptanceCase):
    @acceptance("route", "DEMO-01")
    def test_three_minute_product_path_runs_without_network(self) -> None:
        with simulated_network_failure() as network:
            self.login_demo()

            profile = self.client.get("/profile")
            self.assertEqual(profile.status_code, 200, profile.get_data(as_text=True))
            self.assertIn("SELF ONLY", profile.get_data(as_text=True))

            candidate_id, attempt_id, result_html = self.complete_match_to_result()
            self.assert_contains_smoothed_score(result_html)
            for private_value in (
                "raw_score",
                "MATCH_WEIGHT_GROUPS",
                "external_subject",
                "access_token",
                "password_hash",
            ):
                self.assertNotIn(private_value, result_html)

            conversation = self.client.post(
                f"/matches/{candidate_id}/start",
                data={"attempt_id": attempt_id},
            )
            self.assertEqual(conversation.status_code, 302, conversation.get_data(as_text=True))
            conversation_path = conversation.headers["Location"]
            for tool in ("dice", "task_card", "unlock"):
                response = self.client.post(f"{conversation_path}/tools/{tool}")
                self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
            for _ in range(4):
                response = self.client.post(f"{conversation_path}/demo/advance")
                self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
            l4_html = self.client.get(conversation_path).get_data(as_text=True)
            self.assertIn("L4", l4_html)
            self.assertIn("交换联系方式", l4_html)

            event = self.client.get("/events/event_002")
            self.assertEqual(event.status_code, 200, event.get_data(as_text=True))
            event_html = event.get_data(as_text=True)
            self.assertIn("饭局已成团", event_html)
            self.assertIn("进入匿名群聊", event_html)
            group = self.client.get("/conversations/group_event_002")
            self.assertEqual(group.status_code, 200, group.get_data(as_text=True))
            group_html = group.get_data(as_text=True)
            self.assertIn("匿名", group_html)
            for private_value in ("demo_002", "sora@realtags.local", "password_hash"):
                self.assertNotIn(private_value, group_html)

        network.assert_not_called()

    @acceptance("assertion", "STATE-10")
    def test_searching_and_l0_result_do_not_expose_identity_or_algorithm_fields(self) -> None:
        self.login_demo()
        started = self.client.post("/matches/search/start")
        searching_html = self.client.get(started.headers["Location"]).get_data(as_text=True)
        candidate_id, _, result_html = self.complete_match_to_result()

        for html in (searching_html, result_html):
            for private_value in (
                "夜航星",
                "sora@realtags.local",
                "raw_score",
                "display_score",
                "MATCH_WEIGHT_GROUPS",
                "external_subject",
                "duolingo",
                "github",
                "leetcode",
            ):
                self.assertNotIn(private_value, html)

    @acceptance("assertion", "STATE-10/CORE-001")
    def test_l0_dom_omits_internal_candidate_identifier_after_core_assembly(self) -> None:
        self.require_core_contract()
        self.login_demo()
        candidate_id, _, result_html = self.complete_match_to_result()
        self.assertNotIn(candidate_id, result_html)


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
