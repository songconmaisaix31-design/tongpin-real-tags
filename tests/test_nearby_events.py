from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.config import Config
from app.constants import POIS
from app.db import get_db
from app.services.events import POI_LOCATIONS, list_events, parse_nearby_query
from app.services.users import ValidationError


EXPECTED_TITLES = (
    "AI 从业者交流晚餐",
    "周末跑步后的铜锅聚餐",
    "读书与独立电影分享局",
    "簋街夜宵与城市新朋友",
    "创业者铜锅晚餐",
    "北京味道文化晚餐",
    "英语学习者周末午餐",
    "云南菜与旅行故事局",
)


class NearbyEventsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        config = type(
            "NearbyTestConfig",
            (Config,),
            {
                "TESTING": True,
                "DATABASE": str(Path(self.temp_dir.name) / "test.sqlite3"),
                "SECRET_KEY": "test",
                "DEMO_MODE": True,
            },
        )
        self.config = config
        self.app = create_app(config)
        self.client = self.app.test_client()
        self.client.post("/demo/login")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_beijing_poi_contract_and_demo_upgrade_are_idempotent(self) -> None:
        self.assertEqual(tuple(POIS), tuple(f"poi_{index:03d}" for index in range(1, 9)))
        self.assertEqual(set(POIS), set(POI_LOCATIONS))
        self.assertTrue(all(poi["address"].startswith("北京市") for poi in POIS.values()))
        self.assertTrue(all(location["city"] == "北京" for location in POI_LOCATIONS.values()))

        create_app(self.config)
        with self.app.app_context():
            db = get_db()
            event_count = db.execute("SELECT COUNT(*) AS count FROM events").fetchone()["count"]
            group_count = db.execute(
                "SELECT COUNT(*) AS count FROM conversations WHERE id = 'group_event_002'"
            ).fetchone()["count"]
            member_count = db.execute(
                "SELECT COUNT(*) AS count FROM event_members WHERE event_id = 'event_002'"
            ).fetchone()["count"]

        self.assertEqual(event_count, 8)
        self.assertEqual(group_count, 1)
        self.assertEqual(member_count, 3)

    def test_location_query_filters_and_sorts_by_estimated_distance(self) -> None:
        origin = POI_LOCATIONS["poi_001"]
        args = {
            "lat": str(origin["lat"]),
            "lng": str(origin["lng"]),
            "accuracy": "18.4",
            "radius": "50",
            "sort": "distance",
        }
        with self.app.app_context():
            events = list_events("demo_001", args)
            same_place = list_events("demo_001", {**args, "radius": "0.1"})

        self.assertEqual(
            [event["poi_id"] for event in events],
            ["poi_001", "poi_008", "poi_004", "poi_006", "poi_002", "poi_007", "poi_003", "poi_005"],
        )
        self.assertEqual([event["distance_km"] for event in events], sorted(event["distance_km"] for event in events))
        self.assertEqual([event["poi_id"] for event in same_place], ["poi_001"])

        response = self.client.get("/events", query_string=args)
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        ordered_titles = (
            "AI 从业者交流晚餐",
            "云南菜与旅行故事局",
            "读书与独立电影分享局",
            "北京味道文化晚餐",
            "簋街夜宵与城市新朋友",
            "英语学习者周末午餐",
            "创业者铜锅晚餐",
            "周末跑步后的铜锅聚餐",
        )
        self.assertEqual([html.index(title) for title in ordered_titles], sorted(html.index(title) for title in ordered_titles))
        self.assertEqual(html.count('class="distance-chip"'), 8)
        self.assertIn("距离为估算值", html)
        self.assertIn("你的位置", html)
        self.assertIn("39.9145, 116.4029", html)
        self.assertIn("浏览器精度", html)
        self.assertIn("约 18 m", html)
        self.assertIn("最近白名单 POI", html)
        self.assertIn("四季民福烤鸭店(故宫店)", html)
        self.assertIn("不会保存到你的账户、会话或数据库", html)
        self.assertIn('method="get" action="/events"', html)
        with self.client.session_transaction() as flask_session:
            self.assertNotIn("lat", flask_session)
            self.assertNotIn("lng", flask_session)

    def test_invalid_location_and_radius_are_rejected_then_page_falls_back(self) -> None:
        invalid_queries = (
            {"lat": "91", "lng": "121", "radius": "5"},
            {"lat": "31", "lng": "181", "radius": "5"},
            {"lat": "31", "radius": "5"},
            {"lat": "31", "lng": "121", "radius": "0"},
            {"lat": "31", "lng": "121", "radius": "50.1"},
            {"lat": "nan", "lng": "121", "radius": "5"},
            {"lat": "31", "lng": "121", "accuracy": "nan", "radius": "5"},
        )
        with self.app.app_context():
            for query in invalid_queries:
                with self.subTest(query=query), self.assertRaises(ValidationError):
                    list_events("demo_001", query)

        response = self.client.get(
            "/events", query_string={"lat": "91", "lng": "121", "radius": "5", "sort": "distance"}
        )
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("已回退为城市与全部活动筛选", html)
        for title in EXPECTED_TITLES:
            self.assertIn(title, html)
        self.assertNotIn('class="distance-chip"', html)

    def test_denied_or_unsupported_location_keeps_city_and_all_events(self) -> None:
        html = self.client.get("/events").get_data(as_text=True)
        self.assertIn('name="city"', html)
        self.assertIn("全部城市", html)
        self.assertIn("使用当前位置", html)
        self.assertIn("尚未使用定位", html)
        for title in EXPECTED_TITLES:
            self.assertIn(title, html)

        script_response = self.client.get("/static/js/nearby-events.js")
        script = script_response.get_data(as_text=True)
        script_response.close()
        self.assertLess(script.index('addEventListener("click"'), script.index("getCurrentPosition"))
        self.assertIn("已保留城市筛选和全部活动", script)
        self.assertNotIn("fetch(", script)
        self.assertNotIn("localStorage", script)
        self.assertIn("position.coords.accuracy", script)

    def test_location_summary_uses_the_nearest_whitelisted_poi_and_rounds_for_display(self) -> None:
        nearby = parse_nearby_query({"lat": "39.91454", "lng": "116.40289", "accuracy": "12.7"})

        self.assertEqual(nearby["lat_param"], "39.9145")
        self.assertEqual(nearby["lng_param"], "116.4029")
        self.assertEqual(nearby["accuracy_m"], 13)
        self.assertEqual(nearby["nearest_poi"]["id"], "poi_001")
        self.assertEqual(nearby["nearest_poi"]["distance_km"], 0.0)

    def test_unlocated_listing_preserves_the_existing_service_contract(self) -> None:
        with self.app.app_context():
            events = list_events("demo_001", {})
        self.assertEqual(len(events), 8)
        for event in events:
            self.assertTrue({"id", "title", "display_score", "status_label", "required_tag_labels"} <= event.keys())
            self.assertNotIn("distance_km", event)

        city_html = self.client.get("/events", query_string={"city": "北京"}).get_data(as_text=True)
        for title in EXPECTED_TITLES:
            self.assertIn(title, city_html)
        shanghai_html = self.client.get("/events", query_string={"city": "上海"}).get_data(as_text=True)
        for title in EXPECTED_TITLES:
            self.assertNotIn(title, shanghai_html)


if __name__ == "__main__":
    unittest.main()
