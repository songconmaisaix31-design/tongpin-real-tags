from __future__ import annotations

from urllib.parse import urlencode

from .http import JsonRequest, JsonTransport, request_json
from .models import (
    Clock,
    ExternalTag,
    SourceFailure,
    SourceSyncResult,
    failed_result,
    make_tag,
    normalize_handle,
    utc_timestamp,
)
from .validation import is_non_negative_int, schema_mismatch


SOURCE = "duolingo"
DATA_MODE = "public_live"
MAPPING_VERSION = "duolingo-public-v1"
IDENTITY_ASSURANCE = "unverified_public_handle"
HANDLE_PATTERN = r"[A-Za-z0-9._-]+"
MAX_RESPONSE_BYTES = 64 * 1024


class DuolingoAdapter:
    source = SOURCE

    def __init__(
        self,
        *,
        transport: JsonTransport = request_json,
        clock: Clock = utc_timestamp,
        timeout_seconds: float = 4.0,
    ):
        self._transport = transport
        self._clock = clock
        self._timeout_seconds = timeout_seconds

    def fetch(self, subject: str | None) -> SourceSyncResult:
        attempted_at = self._clock()
        try:
            handle = normalize_handle(subject, HANDLE_PATTERN, 64)
            query = urlencode({"username": handle})
            payload = self._transport(
                JsonRequest(
                    method="GET",
                    url=f"https://www.duolingo.com/2017-06-30/users?{query}",
                    timeout_seconds=self._timeout_seconds,
                    max_bytes=MAX_RESPONSE_BYTES,
                )
            )
            tags = _map_profile(payload, attempted_at)
        except SourceFailure as failure:
            return failed_result(
                source=SOURCE,
                data_mode=DATA_MODE,
                identity_assurance=IDENTITY_ASSURANCE,
                mapping_version=MAPPING_VERSION,
                attempted_at=attempted_at,
                failure=failure,
            )
        return SourceSyncResult(
            source=SOURCE,
            data_mode=DATA_MODE,
            state="ready",
            identity_assurance=IDENTITY_ASSURANCE,
            attempted_at=attempted_at,
            fetched_at=attempted_at,
            mapping_version=MAPPING_VERSION,
            tags=tags,
        )


def _map_profile(payload: object, observed_at: str) -> tuple[ExternalTag, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("users"), list):
        raise schema_mismatch()
    users = payload["users"]
    if not users:
        raise SourceFailure("unavailable", "profile_not_found")
    user = users[0]
    if not isinstance(user, dict):
        raise schema_mismatch()
    streak = user.get("streak")
    total_xp = user.get("totalXp")
    courses = user.get("courses")
    if not is_non_negative_int(streak) or not is_non_negative_int(total_xp) or not isinstance(courses, list):
        raise schema_mismatch()
    current_course_id = user.get("currentCourseId")
    if current_course_id is not None and not isinstance(current_course_id, str):
        raise schema_mismatch()

    course_rows: list[dict[str, object]] = []
    titles_by_language: dict[str, set[str]] = {}
    for course in courses:
        if not isinstance(course, dict):
            raise schema_mismatch()
        language = course.get("learningLanguage")
        xp = course.get("xp")
        if not isinstance(language, str) or not language or not is_non_negative_int(xp):
            raise schema_mismatch()
        course_id = course.get("id")
        title = course.get("title")
        if "id" in course and not isinstance(course_id, str):
            raise schema_mismatch()
        if "title" in course and not isinstance(title, str):
            raise schema_mismatch()
        course_rows.append({"language": language, "xp": xp, "id": course_id})
        if isinstance(title, str):
            titles_by_language.setdefault(language, set()).add(title)

    languages = sorted({str(course["language"]) for course in course_rows})
    titles = {
        language: sorted(titles_by_language[language])[0]
        for language in languages
        if language in titles_by_language
    }
    course_xp = [
        {"language": course["language"], "xp": course["xp"]}
        for course in sorted(course_rows, key=lambda item: (-int(item["xp"]), str(item["language"])))
    ]

    def tag(tag_id: str, name: str, value: dict[str, object]) -> ExternalTag:
        return make_tag(
            tag_id=tag_id,
            category="学习",
            name=name,
            value=value,
            source=SOURCE,
            data_mode=DATA_MODE,
            evidence_kind="direct",
            mapping_version=MAPPING_VERSION,
            observed_at=observed_at,
        )

    tags = [
        tag("learning_languages", "在学语种", {"items": languages, "titles": titles}),
        tag("learning_streak", "连续学习天数", {"days": streak}),
        tag("learning_total_xp", "总学习经验", {"xp": total_xp}),
        tag("learning_course_xp", "分语种学习经验", {"items": course_xp}),
    ]
    if current_course_id is not None:
        current_course = next((course for course in course_rows if course["id"] == current_course_id), None)
        if current_course is not None:
            tags.append(
                tag(
                    "learning_current_course",
                    "当前学习课程",
                    {
                        "course_id": current_course_id,
                        "language": current_course["language"],
                        "xp": current_course["xp"],
                    },
                )
            )
    return tuple(tags)
