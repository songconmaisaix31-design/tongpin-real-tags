from __future__ import annotations

import json

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


SOURCE = "leetcode_com"
DATA_MODE = "public_live"
MAPPING_VERSION = "leetcode-com-public-v1"
IDENTITY_ASSURANCE = "unverified_public_handle"
HANDLE_PATTERN = r"[A-Za-z0-9_-]+"
QUERY = (
    "query PublicProfile($username: String!) { matchedUser(username: $username) { username profile { ranking } "
    "submitStatsGlobal { acSubmissionNum { difficulty count submissions } } } }"
)


class LeetCodeComAdapter:
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
            body = json.dumps(
                {
                    "operationName": "PublicProfile",
                    "query": QUERY,
                    "variables": {"username": handle},
                },
                separators=(",", ":"),
            ).encode("utf-8")
            payload = self._transport(
                JsonRequest(
                    method="POST",
                    url="https://leetcode.com/graphql",
                    timeout_seconds=self._timeout_seconds,
                    max_bytes=32 * 1024,
                    body=body,
                    headers=(("Content-Type", "application/json"),),
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
    if not isinstance(payload, dict) or payload.get("errors"):
        raise schema_mismatch()
    data = payload.get("data")
    if not isinstance(data, dict):
        raise schema_mismatch()
    matched_user = data.get("matchedUser")
    if matched_user is None:
        raise SourceFailure("unavailable", "profile_not_found")
    if not isinstance(matched_user, dict):
        raise schema_mismatch()
    profile = matched_user.get("profile")
    stats = matched_user.get("submitStatsGlobal")
    if not isinstance(profile, dict) or not isinstance(stats, dict):
        raise schema_mismatch()
    ranking = profile.get("ranking")
    if ranking is not None and not is_non_negative_int(ranking):
        raise schema_mismatch()
    submissions = stats.get("acSubmissionNum")
    if not isinstance(submissions, list):
        raise schema_mismatch()

    required = {"All", "Easy", "Medium", "Hard"}
    by_difficulty: dict[str, dict[str, int]] = {}
    for item in submissions:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("difficulty"), str)
            or not is_non_negative_int(item.get("count"))
            or not is_non_negative_int(item.get("submissions"))
        ):
            raise schema_mismatch()
        difficulty = item["difficulty"]
        if difficulty in required:
            if difficulty in by_difficulty:
                raise schema_mismatch()
            by_difficulty[difficulty] = {
                "count": item["count"],
                "submissions": item["submissions"],
            }
    if set(by_difficulty) != required:
        raise schema_mismatch()

    def tag(tag_id: str, name: str, value: dict[str, object]) -> ExternalTag:
        return make_tag(
            tag_id=tag_id,
            category="技术",
            name=name,
            value=value,
            source=SOURCE,
            data_mode=DATA_MODE,
            evidence_kind="direct",
            mapping_version=MAPPING_VERSION,
            observed_at=observed_at,
        )

    tags = [
        tag("coding_solved_total", "公开解题总数", {"count": by_difficulty["All"]["count"]}),
        tag(
            "coding_solved_by_difficulty",
            "分难度公开解题数",
            {
                "easy": by_difficulty["Easy"]["count"],
                "medium": by_difficulty["Medium"]["count"],
                "hard": by_difficulty["Hard"]["count"],
            },
        ),
        tag(
            "coding_accepted_submissions",
            "公开通过提交次数",
            {
                "total": by_difficulty["All"]["submissions"],
                "easy": by_difficulty["Easy"]["submissions"],
                "medium": by_difficulty["Medium"]["submissions"],
                "hard": by_difficulty["Hard"]["submissions"],
            },
        ),
    ]
    if ranking is not None:
        tags.append(tag("coding_public_ranking", "公开排名", {"rank": ranking}))
    return tuple(tags)
