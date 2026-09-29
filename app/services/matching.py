from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from ..constants import MATCH_WEIGHT_GROUPS
from ..db import get_db
from .users import get_user, matching_tags


def validate_weight_groups() -> None:
    for group in MATCH_WEIGHT_GROUPS.values():
        total = sum(group["weights"].values(), Decimal("0"))
        if total != Decimal("1.00"):
            raise AssertionError(f"Match weight group {group['group_key']} must total 1.00, got {total}")


validate_weight_groups()


def _set_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_set, right_set = set(left), set(right)
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 0.0


def _tag_values(user_id: str) -> dict[str, dict]:
    return {tag["tag_id"]: tag["value"] for tag in matching_tags(user_id)}


def _list_value(tags: dict[str, dict], key: str) -> list[str]:
    items = tags.get(key, {}).get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, str)]


def _list_value_aliases(tags: dict[str, dict], *keys: str) -> list[str]:
    for key in keys:
        if key in tags:
            return _list_value(tags, key)
    return []


def _behavior_similarity(left_tags: dict[str, dict], right_tags: dict[str, dict]) -> float:
    """Compare the normalized list signals shared by every datasource mode."""
    signals = []
    for keys in (
        ("learning_languages", "lang_learning"),
        ("sport_primary",),
        ("coding_primary_languages",),
    ):
        left_present = any(key in left_tags for key in keys)
        right_present = any(key in right_tags for key in keys)
        if not left_present and not right_present:
            continue
        signals.append(
            _set_similarity(
                _list_value_aliases(left_tags, *keys),
                _list_value_aliases(right_tags, *keys),
            )
        )
    return sum(signals) / len(signals) if signals else 0.0


def _hours(user: dict, tags: dict[str, dict]) -> list[int]:
    values = set(tags.get("learning_active_hours", {}).get("hours", []))
    values.update(tags.get("sport_active_hours", {}).get("hours", []))
    if not values:
        fallback = {"早鸟": [7, 8], "正常": [12, 19], "夜猫子": [21, 22]}
        values.update(fallback[user["schedule"]])
    return list(values)


def _mbti_similarity(left: str, right: str) -> float:
    if "不知道" in (left, right):
        return 0.0
    return sum(a == b for a, b in zip(left, right)) / 4


def _active_time_similarity(left: dict, left_tags: dict, right: dict, right_tags: dict) -> float:
    return _set_similarity(_hours(left, left_tags), _hours(right, right_tags))


def _has_external_tags(user_id: str) -> bool:
    return bool(matching_tags(user_id))


def smooth_display_score(raw_score: float) -> int:
    """Clamp an internal score and apply the frozen 60-98 presentation transform."""
    bounded = max(0.0, min(1.0, float(raw_score)))
    return round(60 + bounded * 38)


def is_hard_filter_match(viewer: dict, candidate: dict) -> bool:
    viewer_age = date.today().year - viewer["birth_year"]
    candidate_age = date.today().year - candidate["birth_year"]
    if not (18 <= viewer_age <= 100 and 18 <= candidate_age <= 100):
        return False
    viewer_accepts = viewer["match_gender"] == "any" or viewer["match_gender"] == candidate["gender"]
    candidate_accepts = candidate["match_gender"] == "any" or candidate["match_gender"] == viewer["gender"]
    return viewer_accepts and candidate_accepts


def calculate_match(viewer: dict, candidate: dict) -> dict:
    viewer_tags, candidate_tags = _tag_values(viewer["id"]), _tag_values(candidate["id"])
    behavior = _behavior_similarity(viewer_tags, candidate_tags)
    similarities = {
        "purpose": _set_similarity(viewer["purposes"], candidate["purposes"]),
        "behavior": behavior,
        "interests": _set_similarity(viewer["interests"], candidate["interests"]),
        "active_time": _active_time_similarity(viewer, viewer_tags, candidate, candidate_tags),
        "city": 1.0 if viewer["city"] == candidate["city"] else 0.0,
        "mbti": _mbti_similarity(viewer["mbti"], candidate["mbti"]),
    }
    group = MATCH_WEIGHT_GROUPS["default" if _has_external_tags(viewer["id"]) else "no_external_data"]
    raw = sum(float(weight) * similarities[key] for key, weight in group["weights"].items())
    raw = max(0.0, min(1.0, raw))
    return {
        "raw_score": raw,
        "display_score": smooth_display_score(raw),
        "common_point_count": max(1, round(sum(value > 0 for value in similarities.values()))),
    }


def ranked_matches(viewer_id: str) -> list[dict]:
    viewer = get_user(viewer_id)
    rows = get_db().execute(
        """SELECT candidate.id
           FROM users AS candidate
           WHERE candidate.id != ?
             AND candidate.is_demo = ?
             AND NOT EXISTS (
               SELECT 1 FROM blocks
               WHERE (blocker_id = ? AND blocked_id = candidate.id)
                  OR (blocker_id = candidate.id AND blocked_id = ?)
             )""",
        (viewer_id, int(bool(viewer["is_demo"])), viewer_id, viewer_id),
    ).fetchall()
    matches = []
    for row in rows:
        candidate = get_user(row["id"])
        if not is_hard_filter_match(viewer, candidate):
            continue
        score = calculate_match(viewer, candidate)
        matches.append({"candidate": candidate, **score})
    return sorted(matches, key=lambda item: item["raw_score"], reverse=True)


def event_match_score(user_id: str, required_tags: list[str]) -> dict:
    """Event matching reuses normalized tag identifiers and the presentation smoothing policy."""
    user = get_user(user_id)
    behavior_tags = _tag_values(user_id)
    known = set(user["interests"])
    if "人工智能" in user["interests"]:
        known.add("interest_ai")
    if "创业" in user["interests"]:
        known.add("identity_startup")
    language_map = {
        "en": "lang_learning_en",
        "英语": "lang_learning_en",
        "ja": "lang_learning_ja",
        "日语": "lang_learning_ja",
    }
    sport_map = {"跑步": "sport_running", "瑜伽": "sport_yoga"}
    known.update(
        language_map.get(item)
        for item in _list_value_aliases(behavior_tags, "learning_languages", "lang_learning")
    )
    known.update(sport_map.get(item) for item in _list_value(behavior_tags, "sport_primary"))
    known.discard(None)
    matches = known & set(required_tags)
    raw = len(matches) / len(required_tags) if required_tags else 0.0
    return {"raw_score": raw, "display_score": smooth_display_score(raw), "common_tag_count": len(matches)}


def event_required_tags(event_row) -> list[str]:
    return json.loads(event_row["required_tags_json"])
