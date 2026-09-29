from __future__ import annotations

from collections import Counter
from urllib.parse import quote

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
from .validation import is_non_negative_int, parse_upstream_timestamp, schema_mismatch


SOURCE = "github"
DATA_MODE = "public_live"
MAPPING_VERSION = "github-rest-public-v1"
IDENTITY_ASSURANCE = "unverified_public_handle"
HANDLE_PATTERN = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"


class GitHubAdapter:
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
            handle = normalize_handle(subject, HANDLE_PATTERN, 39)
            encoded_handle = quote(handle, safe="")
            base_url = f"https://api.github.com/users/{encoded_handle}"
            user = self._transport(self._request(base_url, 32 * 1024))
            repositories = self._transport(
                self._request(
                    f"{base_url}/repos?sort=pushed&direction=desc&type=owner&per_page=10&page=1",
                    128 * 1024,
                )
            )
            events = self._transport(
                self._request(f"{base_url}/events?per_page=10&page=1", 128 * 1024)
            )
            tags = _map_profile(user, repositories, events, attempted_at)
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

    def _request(self, url: str, max_bytes: int) -> JsonRequest:
        return JsonRequest(
            method="GET",
            url=url,
            timeout_seconds=self._timeout_seconds,
            max_bytes=max_bytes,
        )


def _map_profile(
    user: object,
    repositories: object,
    events: object,
    observed_at: str,
) -> tuple[ExternalTag, ...]:
    if (
        not isinstance(user, dict)
        or not isinstance(user.get("login"), str)
        or not user["login"]
        or not is_non_negative_int(user.get("public_repos"))
        or not isinstance(repositories, list)
        or not isinstance(events, list)
    ):
        raise schema_mismatch()

    non_fork_languages: list[str] = []
    non_fork_count = 0
    sampled_repositories = repositories[:10]
    for repository in sampled_repositories:
        if not isinstance(repository, dict) or type(repository.get("fork")) is not bool:
            raise schema_mismatch()
        if "language" not in repository or "pushed_at" not in repository:
            raise schema_mismatch()
        language = repository.get("language")
        pushed_at = repository.get("pushed_at")
        if language is not None and not isinstance(language, str):
            raise schema_mismatch()
        if pushed_at is not None:
            parse_upstream_timestamp(pushed_at)
        if not repository["fork"]:
            non_fork_count += 1
            if isinstance(language, str) and language:
                non_fork_languages.append(language)

    event_counts: Counter[str] = Counter()
    activity_days: set[str] = set()
    sampled_events = events[:10]
    for event in sampled_events:
        if not isinstance(event, dict) or not isinstance(event.get("type"), str) or not event["type"]:
            raise schema_mismatch()
        created_at = parse_upstream_timestamp(event.get("created_at"))
        event_counts[event["type"]] += 1
        activity_days.add(created_at.date().isoformat())

    def tag(
        tag_id: str,
        name: str,
        value: dict[str, object],
        *,
        evidence_kind: str = "direct",
    ) -> ExternalTag:
        return make_tag(
            tag_id=tag_id,
            category="技术",
            name=name,
            value=value,
            source=SOURCE,
            data_mode=DATA_MODE,
            evidence_kind=evidence_kind,
            mapping_version=MAPPING_VERSION,
            observed_at=observed_at,
        )

    tags = [
        tag("coding_public_repositories", "公开仓库数量", {"count": user["public_repos"]}),
    ]
    if non_fork_languages:
        language_counts = Counter(non_fork_languages)
        ordered_languages = sorted(language_counts, key=lambda language: (-language_counts[language], language))
        tags.append(
            tag(
                "coding_primary_languages",
                "公开仓库主要语言",
                {
                    "items": ordered_languages,
                    "sample_size": non_fork_count,
                    "window": "latest_10_owner_repositories",
                },
            )
        )
    tags.extend(
        [
            tag(
                "coding_recent_event_types",
                "近期公开活动类型",
                {
                    "counts": {event_type: event_counts[event_type] for event_type in sorted(event_counts)},
                    "event_count": len(sampled_events),
                    "window": "latest_10_public_events",
                },
            ),
            tag(
                "coding_recent_activity_days",
                "近期公开活跃天数",
                {
                    "days": len(activity_days),
                    "event_count": len(sampled_events),
                    "window": "latest_10_public_events",
                },
                evidence_kind="derived",
            ),
        ]
    )
    return tuple(tags)
