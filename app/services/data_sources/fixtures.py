from __future__ import annotations

import hashlib

from .models import Clock, ExternalTag, SourceSyncResult, make_tag, utc_timestamp


OFFLINE_FIXTURE_VERSION = "offline-fixture-v1"


def _source_seed(mapping_version: str, user_id: str, source: str) -> int:
    material = f"{mapping_version}:{user_id}:{source}".encode("utf-8")
    return int(hashlib.sha256(material).hexdigest()[:8], 16)


def offline_fixture_tags(
    user_id: str,
    *,
    mapping_version: str = OFFLINE_FIXTURE_VERSION,
) -> tuple[ExternalTag, ...]:
    duolingo_seed = _source_seed(mapping_version, user_id, "duolingo")
    keep_seed = _source_seed(mapping_version, user_id, "keep")
    github_seed = _source_seed(mapping_version, user_id, "github")
    leetcode_seed = _source_seed(mapping_version, user_id, "leetcode_com")
    streak = 180 + duolingo_seed % 180
    weekly = 3 + keep_seed % 3
    public_repositories = 8 + github_seed % 12
    solved = 120 + leetcode_seed % 180

    def tag(
        source: str,
        tag_id: str,
        category: str,
        name: str,
        value: dict[str, object],
        *,
        evidence_kind: str = "direct",
    ) -> ExternalTag:
        return make_tag(
            tag_id=tag_id,
            category=category,
            name=name,
            value=value,
            source=source,
            data_mode="fixture",
            evidence_kind=evidence_kind,
            mapping_version=mapping_version,
            observed_at=None,
        )

    return (
        tag("duolingo", "learning_languages", "学习", "在学语种", {"items": ["en", "ja"], "titles": {"en": "English", "ja": "Japanese"}}),
        tag("duolingo", "learning_streak", "学习", "连续学习天数", {"days": streak}),
        tag("duolingo", "learning_total_xp", "学习", "总学习经验", {"xp": streak * 52}),
        tag("duolingo", "learning_course_xp", "学习", "分语种学习经验", {"items": [{"language": "en", "xp": streak * 35}, {"language": "ja", "xp": streak * 17}]}),
        tag("duolingo", "learning_current_course", "学习", "当前学习课程", {"course_id": "fixture-course-en", "language": "en", "xp": streak * 35}),
        tag("duolingo", "learning_consistency", "学习", "学习坚持度", {"level": "硬核" if streak >= 250 else "稳定"}, evidence_kind="derived"),
        tag("duolingo", "learning_active_hours", "学习", "学习活跃时段", {"hours": [21, 22]}, evidence_kind="derived"),
        tag("duolingo", "learning_level", "学习", "当前学习等级", {"level": 8 + duolingo_seed % 7}, evidence_kind="derived"),
        tag("keep", "sport_primary", "运动", "主要运动类型", {"items": ["跑步", "瑜伽"]}),
        tag("keep", "sport_weekly", "运动", "周运动频次", {"times": weekly}),
        tag("keep", "sport_total", "运动", "累计运动量", {"km": weekly * 72, "minutes": weekly * 260}),
        tag("keep", "sport_active_hours", "运动", "运动活跃时段", {"hours": [6, 19]}),
        tag("keep", "sport_intensity", "运动", "运动强度等级", {"level": "进阶"}),
        tag("github", "coding_public_repositories", "技术", "公开仓库数量", {"count": public_repositories}),
        tag("github", "coding_primary_languages", "技术", "公开仓库主要语言", {"items": ["Python", "TypeScript"], "sample_size": 8, "window": "latest_10_owner_repositories"}),
        tag("github", "coding_recent_event_types", "技术", "近期公开活动类型", {"counts": {"PushEvent": 4, "WatchEvent": 1}, "event_count": 5, "window": "latest_10_public_events"}),
        tag("github", "coding_recent_activity_days", "技术", "近期公开活跃天数", {"days": 3, "event_count": 5, "window": "latest_10_public_events"}, evidence_kind="derived"),
        tag("leetcode_com", "coding_solved_total", "技术", "公开解题总数", {"count": solved}),
        tag("leetcode_com", "coding_solved_by_difficulty", "技术", "分难度公开解题数", {"easy": solved // 2, "medium": solved // 3, "hard": solved - solved // 2 - solved // 3}),
        tag("leetcode_com", "coding_accepted_submissions", "技术", "公开通过提交次数", {"total": solved * 2, "easy": solved, "medium": solved * 2 // 3, "hard": solved // 3}),
        tag("leetcode_com", "coding_public_ranking", "技术", "公开排名", {"rank": 100000 + leetcode_seed % 500000}),
    )


class KeepFixtureAdapter:
    source = "keep"

    def __init__(self, *, clock: Clock = utc_timestamp):
        self._clock = clock

    def fetch(self, subject: str | None) -> SourceSyncResult:
        attempted_at = self._clock()
        mapping_version = "keep-fixture-v1"
        tags = tuple(
            tag
            for tag in offline_fixture_tags(subject or "fixture-user", mapping_version=mapping_version)
            if tag.source == self.source
        )
        return SourceSyncResult(
            source=self.source,
            data_mode="fixture",
            state="ready",
            identity_assurance="synthetic_fixture",
            attempted_at=attempted_at,
            fetched_at=None,
            mapping_version=mapping_version,
            tags=tags,
        )
