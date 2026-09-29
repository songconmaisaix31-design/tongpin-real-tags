from __future__ import annotations

try:
    from .support import AcceptanceCase, acceptance
except ImportError:  # Direct discovery with tests/acceptance as the start directory.
    from support import AcceptanceCase, acceptance


class ProductBoundaryAcceptanceTests(AcceptanceCase):
    @acceptance("auth", "AUTH-01")
    def test_guest_and_nonmember_requests_cannot_mutate_product_state(self) -> None:
        tracked_tables = ("conversations", "messages", "events", "event_members", "reports", "blocks")
        before = {table: self.row_count(table) for table in tracked_tables}

        for path, data in (
            ("/matches/search/start", {}),
            ("/conversations/group_event_002/messages", {"content": "guest write"}),
            ("/events/event_001/signup", {}),
            ("/events/event_001/report", {"reason": "guest report"}),
        ):
            with self.subTest(path=path):
                response = self.client.post(path, data=data)
                self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
                self.assertTrue(response.headers["Location"].endswith("/login"))

        outsider, _ = self.register_user(email="outsider@example.test", alias="边界访客")
        self.assertEqual(outsider.get("/conversations/group_event_002").status_code, 404)
        outsider.post("/conversations/group_event_002/messages", data={"content": "nonmember write"})
        outsider.post(
            "/conversations/group_event_002/report",
            data={"reason": "nonmember report"},
        )

        after = {table: self.row_count(table) for table in tracked_tables}
        self.assertEqual(after, before)

    @acceptance("input", "INPUT-01")
    def test_invalid_forms_and_stale_attempts_have_no_domain_side_effects(self) -> None:
        self.login_demo()

        event_count = self.row_count("events")
        response = self.client.post("/events/new", data=self.event_form(poi_id="private-home"))
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(self.row_count("events"), event_count)

        message_count = self.row_count("messages", "conversation_id = ?", ("group_event_002",))
        response = self.client.post(
            "/conversations/group_event_002/messages",
            data={"content": "x" * 501},
        )
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        self.assertEqual(
            self.row_count("messages", "conversation_id = ?", ("group_event_002",)),
            message_count,
        )

        conversation_count = self.row_count("conversations", "type = 'direct'")
        response = self.client.post(
            "/matches/demo_002/start",
            data={"attempt_id": "forged-attempt"},
        )
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        self.assertEqual(self.row_count("conversations", "type = 'direct'"), conversation_count)


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
