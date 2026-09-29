from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from werkzeug.datastructures import MultiDict

from app import create_app
from app.config import Config
from app.constants import MATCH_WEIGHT_GROUPS, POIS
from app.db import get_db
from app.services.chat import (
    advance_demo_progress,
    block_counterpart,
    get_conversation,
    send_message,
    start_direct_conversation,
    use_tool,
)
from app.services.events import (
    cancel_event,
    create_user_event,
    get_event,
    list_events,
    refresh_event_statuses,
    review_applicants,
    review_signup,
    signup_for_event,
)
from app.services.matching import (
    calculate_match,
    is_hard_filter_match,
    ranked_matches,
    smooth_display_score,
)
from app.services.users import ValidationError, get_user, matching_tags


class CoreContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        config = type(
            "CoreContractConfig",
            (Config,),
            {
                "TESTING": True,
                "DATABASE": str(Path(self.temp_dir.name) / "core-contracts.sqlite3"),
                "SECRET_KEY": "core-contract-test-key",
                "DEMO_MODE": True,
            },
        )
        self.app = create_app(config)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _login_demo(self) -> None:
        response = self.client.post("/demo/login")
        self.assertEqual(response.status_code, 302)

    @staticmethod
    def _event_form(*, max_size: int = 4, poi_id: str = "poi_001") -> MultiDict:
        start = (datetime.now(timezone.utc) + timedelta(days=30)).replace(
            minute=0, second=0, microsecond=0
        )
        return MultiDict(
            {
                "title": "Contract boundary dinner",
                "description": "A bounded restaurant event.",
                "poi_id": poi_id,
                "start_at": start.isoformat(),
                "signup_deadline": (start - timedelta(days=1)).isoformat(),
                "min_size": "3",
                "max_size": str(max_size),
                "required_tags": "interest_ai",
                "budget_level": "50-100",
                "pay_type": "AA",
                "gender_policy": "any",
                "signup_mode": "review",
            }
        )

    def _replace_normalized_tags(self, data_mode: str, verified: bool) -> None:
        db = get_db()
        columns = {row["name"] for row in db.execute("PRAGMA table_info(tags)").fetchall()}
        if "data_mode" not in columns:
            db.execute("ALTER TABLE tags ADD COLUMN data_mode TEXT NOT NULL DEFAULT 'fixture'")
        db.execute("DELETE FROM tags WHERE user_id IN ('demo_001', 'demo_002')")
        values = {
            "learning_languages": {"items": ["en", "ja"]},
            "sport_primary": {"items": ["running", "yoga"]},
            "coding_primary_languages": {
                "items": ["Python", "TypeScript"],
                "sample_size": 4,
                "window": "latest_10_owner_repositories",
            },
        }
        for user_id in ("demo_001", "demo_002"):
            for tag_id, value in values.items():
                db.execute(
                    """INSERT INTO tags
                       (user_id, tag_id, category, name, value_json, source, verified,
                        visibility, updated_at, data_mode)
                       VALUES (?, ?, 'behavior', ?, ?, 'contract-test', ?, 'self_only', ?, ?)""",
                    (
                        user_id,
                        tag_id,
                        tag_id,
                        json.dumps(value),
                        int(verified),
                        datetime.now(timezone.utc).isoformat(),
                        data_mode,
                    ),
                )
        db.commit()

    def test_reciprocal_filters_exact_weight_groups_and_smoothing(self) -> None:
        expected = {
            "default": {
                "purpose": Decimal("0.30"),
                "behavior": Decimal("0.25"),
                "interests": Decimal("0.20"),
                "active_time": Decimal("0.15"),
                "city": Decimal("0.05"),
                "mbti": Decimal("0.05"),
            },
            "no_external_data": {
                "purpose": Decimal("0.45"),
                "interests": Decimal("0.30"),
                "active_time": Decimal("0.15"),
                "city": Decimal("0.05"),
                "mbti": Decimal("0.05"),
            },
        }
        self.assertEqual({key: value["weights"] for key, value in MATCH_WEIGHT_GROUPS.items()}, expected)
        for key, group in MATCH_WEIGHT_GROUPS.items():
            self.assertEqual(group["group_key"], key)
            self.assertEqual(sum(group["weights"].values(), Decimal("0")), Decimal("1.00"))
        self.assertEqual(smooth_display_score(-1), 60)
        self.assertEqual(smooth_display_score(0), 60)
        self.assertEqual(smooth_display_score(1), 98)
        self.assertEqual(smooth_display_score(2), 98)

        with self.app.app_context():
            viewer = deepcopy(get_user("demo_001"))
            candidate = deepcopy(get_user("demo_002"))
        viewer.update(gender="female", match_gender="male")
        candidate.update(gender="male", match_gender="female")
        self.assertTrue(is_hard_filter_match(viewer, candidate))
        candidate["match_gender"] = "male"
        self.assertFalse(is_hard_filter_match(viewer, candidate))
        candidate["match_gender"] = "female"
        candidate["birth_year"] = date.today().year - 17
        self.assertFalse(is_hard_filter_match(viewer, candidate))

    def test_public_and_fixture_tags_share_one_private_behavior_boundary(self) -> None:
        with self.app.app_context():
            self._replace_normalized_tags("public_live", True)
            viewer, candidate = get_user("demo_001"), get_user("demo_002")
            public_tags = matching_tags(viewer["id"])
            public_score = calculate_match(viewer, candidate)
            self.assertAlmostEqual(public_score["raw_score"], 0.7075)
            self.assertEqual(
                {tag["tag_id"] for tag in public_tags},
                {"learning_languages", "sport_primary", "coding_primary_languages"},
            )
            self.assertTrue(all(set(tag) == {"tag_id", "value"} for tag in public_tags))

            self._replace_normalized_tags("fixture", False)
            fixture_tags = matching_tags(viewer["id"])
            fixture_score = calculate_match(viewer, candidate)
            self.assertEqual(public_score, fixture_score)
            self.assertEqual(public_tags, fixture_tags)

            baseline_raw = fixture_score["raw_score"]
            mismatches = {
                "learning_languages": {"items": ["fr"]},
                "sport_primary": {"items": ["cycling"]},
                "coding_primary_languages": {
                    "items": ["Rust"],
                    "sample_size": 1,
                    "window": "latest_10_owner_repositories",
                },
            }
            for tag_id, mismatch in mismatches.items():
                with self.subTest(tag_id=tag_id):
                    original = next(tag["value"] for tag in fixture_tags if tag["tag_id"] == tag_id)
                    get_db().execute(
                        """UPDATE tags SET value_json = ?
                           WHERE user_id = 'demo_002' AND tag_id = ?""",
                        (json.dumps(mismatch), tag_id),
                    )
                    get_db().commit()
                    self.assertLess(calculate_match(viewer, candidate)["raw_score"], baseline_raw)
                    get_db().execute(
                        """UPDATE tags SET value_json = ?
                           WHERE user_id = 'demo_002' AND tag_id = ?""",
                        (json.dumps(original), tag_id),
                    )
                    get_db().commit()

        production_config = type(
            "ProductionCoreContractConfig",
            (Config,),
            {
                "TESTING": True,
                "DATABASE": self.app.config["DATABASE"],
                "SECRET_KEY": "core-contract-test-key",
                "DEMO_MODE": False,
            },
        )
        production_app = create_app(production_config)
        with production_app.app_context():
            self.assertEqual(matching_tags("demo_001"), [])
            viewer, candidate = get_user("demo_001"), get_user("demo_002")
            self.assertAlmostEqual(calculate_match(viewer, candidate)["raw_score"], 0.5675)

    def test_one_active_attempt_and_l0_dom_do_not_expose_candidate_data(self) -> None:
        self._login_demo()
        self.client.post("/matches/search/start")
        with self.client.session_transaction() as flask_session:
            first_flow = dict(flask_session["match_flow"])
        self.client.post("/matches/search/start")
        with self.client.session_transaction() as flask_session:
            self.assertEqual(flask_session["match_flow"]["attempt_id"], first_flow["attempt_id"])

        searching = self.client.get("/matches/searching").get_data(as_text=True)
        for private_value in (first_flow["candidate_id"], "raw_score", "MATCH_WEIGHT_GROUPS", "夜航星"):
            self.assertNotIn(private_value, searching)
        self.assertEqual(self.client.get("/matches/demo_003").status_code, 404)

        completed = self.client.post(
            "/matches/search/complete", data={"attempt_id": first_flow["attempt_id"]}
        )
        result_html = self.client.get(completed.headers["Location"]).get_data(as_text=True)
        with self.app.app_context():
            candidate = get_user(first_flow["candidate_id"])
        for private_value in (
            first_flow["candidate_id"],
            candidate["email"],
            candidate["mbti"],
            str(candidate["birth_year"]),
            "raw_score",
            "weights",
        ):
            self.assertNotIn(private_value, result_html)
        self.assertIn(first_flow["attempt_id"], result_html)

        retry = self.client.post(
            "/matches/search/retry", data={"attempt_id": first_flow["attempt_id"]}
        )
        self.assertEqual(retry.status_code, 302)
        with self.client.session_transaction() as flask_session:
            second_flow = dict(flask_session["match_flow"])
        self.assertNotEqual(second_flow["attempt_id"], first_flow["attempt_id"])
        stale = self.client.post(
            "/matches/search/complete", data={"attempt_id": first_flow["attempt_id"]}
        )
        self.assertTrue(stale.headers["Location"].endswith("/matches"))
        with self.client.session_transaction() as flask_session:
            self.assertEqual(flask_session["match_flow"]["attempt_id"], second_flow["attempt_id"])

    def test_reveal_choice_is_per_viewer_and_blocks_stop_all_interaction(self) -> None:
        with self.app.app_context():
            conversation_id = start_direct_conversation("demo_001", "demo_002")
            left_l0 = get_conversation(conversation_id, "demo_001")
            right_l0 = get_conversation(conversation_id, "demo_002")
            self.assertEqual(left_l0["progress"]["level"], 0)
            self.assertEqual(right_l0["progress"]["level"], 0)
            self.assertEqual(set(left_l0["counterpart"]), {"anonymous_alias", "level"})

            self.assertEqual(advance_demo_progress(conversation_id, "demo_001"), 1)
            left_l1 = get_conversation(conversation_id, "demo_001")
            right_still_l0 = get_conversation(conversation_id, "demo_002")
            self.assertEqual(left_l1["progress"]["level"], 1)
            self.assertIn("city", left_l1["counterpart"])
            self.assertEqual(right_still_l0["progress"]["level"], 0)
            self.assertNotIn("city", right_still_l0["counterpart"])

            now = datetime.now(timezone.utc)
            db = get_db()
            for index in range(8):
                db.execute(
                    """INSERT INTO messages
                       (conversation_id, sender_id, message_type, content, metadata_json, created_at)
                       VALUES (?, 'demo_001', 'text', ?, '{}', ?)""",
                    (conversation_id, f"left-{index}", (now - timedelta(days=index % 3)).isoformat()),
                )
            for index in range(2):
                db.execute(
                    """INSERT INTO messages
                       (conversation_id, sender_id, message_type, content, metadata_json, created_at)
                       VALUES (?, 'demo_002', 'text', ?, '{}', ?)""",
                    (conversation_id, f"right-{index}", now.isoformat()),
                )
            db.commit()
            self.assertEqual(get_conversation(conversation_id, "demo_002")["progress"]["level"], 1)

            with self.assertRaises(ValidationError):
                advance_demo_progress(conversation_id, "demo_003")
            block_counterpart("demo_001", conversation_id)
            for action in (
                lambda: send_message(conversation_id, "demo_001", "blocked"),
                lambda: send_message(conversation_id, "demo_002", "blocked"),
                lambda: use_tool(conversation_id, "demo_001", "dice"),
                lambda: advance_demo_progress(conversation_id, "demo_002"),
            ):
                with self.assertRaises(ValidationError):
                    action()
            self.assertNotIn(
                "demo_002", [item["candidate"]["id"] for item in ranked_matches("demo_001")]
            )
            self.assertNotIn(
                "demo_001", [item["candidate"]["id"] for item in ranked_matches("demo_002")]
            )

    def test_event_creation_review_and_capacity_keep_identity_and_restaurant_boundaries(self) -> None:
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE users SET phone_verified = 0 WHERE id = 'demo_004'")
            db.commit()
            with self.assertRaisesRegex(ValidationError, "手机号"):
                create_user_event("demo_004", self._event_form())
            with self.assertRaisesRegex(ValidationError, "餐厅"):
                create_user_event("demo_001", self._event_form(poi_id="private_address"))
            with self.assertRaisesRegex(ValidationError, "人数"):
                create_user_event("demo_001", self._event_form(max_size=11))

            event_id = create_user_event("demo_001", self._event_form(max_size=3))
            db.execute("UPDATE events SET status = 'recruiting' WHERE id = ?", (event_id,))
            db.commit()
            for user_id in ("demo_002", "demo_003", "demo_004"):
                signup_for_event(event_id, user_id)

            applicants = review_applicants(event_id, "demo_001")
            self.assertEqual(len(applicants), 3)
            self.assertTrue(all("user_id" not in applicant for applicant in applicants))
            serialized = json.dumps(applicants)
            for user_id in ("demo_002", "demo_003", "demo_004"):
                self.assertNotIn(user_id, serialized)

            review_signup(event_id, "demo_001", applicants[0]["review_token"], True)
            review_signup(event_id, "demo_001", applicants[1]["review_token"], True)
            with self.assertRaisesRegex(ValidationError, "人数已满"):
                review_signup(event_id, "demo_001", applicants[2]["review_token"], True)

            event = get_event(event_id, "demo_001")
            self.assertIn(event["poi_id"], POIS)
            self.assertEqual(event["approved_count"], 3)
            self.assertNotIn("raw_score", event)
            self.assertTrue(all("raw_score" not in item for item in list_events("demo_001", {})))

        self._login_demo()
        page = self.client.get(f"/events/{event_id}").get_data(as_text=True)
        for user_id in ("demo_002", "demo_003", "demo_004"):
            self.assertNotIn(user_id, page)
        invalid = self.client.post(
            f"/events/{event_id}/review/{applicants[2]['review_token']}/invalid"
        )
        self.assertEqual(invalid.status_code, 302)
        with self.app.app_context():
            pending_count = get_db().execute(
                """SELECT COUNT(*) AS count FROM event_members
                   WHERE event_id = ? AND membership_status = 'pending'""",
                (event_id,),
            ).fetchone()["count"]
            self.assertEqual(pending_count, 1)
            cancel_event(event_id, "demo_001")
            pending_count = get_db().execute(
                """SELECT COUNT(*) AS count FROM event_members
                   WHERE event_id = ? AND membership_status = 'pending'""",
                (event_id,),
            ).fetchone()["count"]
            self.assertEqual(pending_count, 0)
            self.assertEqual(get_event(event_id, "demo_001")["status"], "cancelled")

    def test_deadlines_reject_late_members_and_ended_groups_archive(self) -> None:
        with self.app.app_context():
            db = get_db()
            past = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.execute(
                "UPDATE events SET signup_deadline = ? WHERE id = 'event_001'",
                (past.isoformat(),),
            )
            db.commit()
            with self.assertRaisesRegex(ValidationError, "截止"):
                signup_for_event("event_001", "demo_004")
            db.execute("UPDATE events SET status = 'cancelled' WHERE id = 'event_001'")

            old_start = datetime.now(timezone.utc) - timedelta(days=8)
            db.execute(
                "UPDATE events SET status = 'ended', start_at = ? WHERE id = 'event_002'",
                (old_start.isoformat(),),
            )
            db.execute(
                "UPDATE conversations SET archived_at = NULL WHERE event_id = 'event_002'"
            )
            db.commit()
            self.assertEqual(refresh_event_statuses(), 0)
            archived = db.execute(
                "SELECT archived_at FROM conversations WHERE event_id = 'event_002'"
            ).fetchone()
            self.assertIsNotNone(archived["archived_at"])


if __name__ == "__main__":
    unittest.main()
