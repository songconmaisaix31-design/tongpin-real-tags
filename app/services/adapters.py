from __future__ import annotations

import json
from collections.abc import Mapping

from flask import current_app

from ..db import get_db
from .data_sources.duolingo import DuolingoAdapter
from .data_sources.fixtures import KeepFixtureAdapter
from .data_sources.github import GitHubAdapter
from .data_sources.http import JsonTransport, request_json
from .data_sources.leetcode import LeetCodeComAdapter
from .data_sources.models import (
    Clock,
    DataSourceAdapter,
    ExternalTag,
    SourceDefinition,
    SourceFailure,
    SourceSyncResult,
    failed_result,
    utc_timestamp,
)


class AdapterError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def get_source_registry(
    *,
    timeout_seconds: float = 4.0,
    transport: JsonTransport = request_json,
    clock: Clock = utc_timestamp,
) -> dict[str, SourceDefinition]:
    """Return the one server-owned registry used by routes and synchronization."""
    definitions = (
        SourceDefinition(
            source_id="duolingo",
            label="多邻国 Duolingo",
            code="DUO",
            data_mode="public_live",
            enabled=True,
            mapping_version="duolingo-public-v1",
            identity_assurance="unverified_public_handle",
            description="同步公开学习语种、连续学习天数与经验值。",
            input_label="Duolingo 公开用户名",
            input_hint="例如 duo",
            input_pattern=r"[A-Za-z0-9._-]+",
            input_max_length=64,
            unavailable_reason=None,
            adapter=DuolingoAdapter(transport=transport, clock=clock, timeout_seconds=timeout_seconds),
        ),
        SourceDefinition(
            source_id="github",
            label="GitHub",
            code="GH",
            data_mode="public_live",
            enabled=True,
            mapping_version="github-rest-public-v1",
            identity_assurance="unverified_public_handle",
            description="同步公开仓库语言与最近 10 条公开活动样本。",
            input_label="GitHub 公开用户名",
            input_hint="例如 octocat",
            input_pattern=r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?",
            input_max_length=39,
            unavailable_reason=None,
            adapter=GitHubAdapter(transport=transport, clock=clock, timeout_seconds=timeout_seconds),
        ),
        SourceDefinition(
            source_id="leetcode_com",
            label="LeetCode.com",
            code="LC",
            data_mode="public_live",
            enabled=True,
            mapping_version="leetcode-com-public-v1",
            identity_assurance="unverified_public_handle",
            description="同步公开解题数量、提交次数与公开排名。",
            input_label="LeetCode.com 公开用户名",
            input_hint="例如 leetcode",
            input_pattern=r"[A-Za-z0-9_-]+",
            input_max_length=64,
            unavailable_reason=None,
            adapter=LeetCodeComAdapter(transport=transport, clock=clock, timeout_seconds=timeout_seconds),
        ),
        SourceDefinition(
            source_id="keep",
            label="Keep",
            code="KEEP",
            data_mode="fixture",
            enabled=True,
            mapping_version="keep-fixture-v1",
            identity_assurance="synthetic_fixture",
            description="载入固定的运动偏好演示数据，不连接 Keep 账号。",
            input_label=None,
            input_hint=None,
            input_pattern=None,
            input_max_length=None,
            unavailable_reason=None,
            adapter=KeepFixtureAdapter(clock=clock),
        ),
        SourceDefinition(
            source_id="netease",
            label="网易云音乐",
            code="163",
            data_mode="unavailable",
            enabled=False,
            mapping_version="none",
            identity_assurance="not_applicable",
            description="音乐行为数据源预留位。",
            input_label=None,
            input_hint=None,
            input_pattern=None,
            input_max_length=None,
            unavailable_reason="缺少经验证且无需账号凭据的安全公开映射。",
            adapter=None,
        ),
        SourceDefinition(
            source_id="weread",
            label="微信读书",
            code="READ",
            data_mode="unavailable",
            enabled=False,
            mapping_version="none",
            identity_assurance="not_applicable",
            description="阅读行为数据源预留位。",
            input_label=None,
            input_hint=None,
            input_pattern=None,
            input_max_length=None,
            unavailable_reason="现有接口需要会话凭据，且公开读取路径未验证。",
            adapter=None,
        ),
        SourceDefinition(
            source_id="steam",
            label="Steam",
            code="STM",
            data_mode="unavailable",
            enabled=False,
            mapping_version="none",
            identity_assurance="not_applicable",
            description="游戏行为数据源预留位。",
            input_label=None,
            input_hint=None,
            input_pattern=None,
            input_max_length=None,
            unavailable_reason="有用映射需要 API key，本次演示不读取凭据。",
            adapter=None,
        ),
        SourceDefinition(
            source_id="github_graphql",
            label="GitHub GraphQL",
            code="GHQL",
            data_mode="unavailable",
            enabled=False,
            mapping_version="none",
            identity_assurance="not_applicable",
            description="GitHub 私有或聚合数据预留位。",
            input_label=None,
            input_hint=None,
            input_pattern=None,
            input_max_length=None,
            unavailable_reason="GraphQL 需要认证；P0 仅使用公开 REST。",
            adapter=None,
        ),
        SourceDefinition(
            source_id="leetcode_cn",
            label="LeetCode.cn",
            code="LCCN",
            data_mode="unavailable",
            enabled=False,
            mapping_version="none",
            identity_assurance="not_applicable",
            description="力扣中国站公开资料预留位。",
            input_label=None,
            input_hint=None,
            input_pattern=None,
            input_max_length=None,
            unavailable_reason="仅验证了传输可达性，尚无冻结的产品字段映射。",
            adapter=None,
        ),
    )
    return {definition.source_id: definition for definition in definitions}


def source_connection_states(user_id: str) -> dict[str, dict[str, object]]:
    rows = get_db().execute(
        """SELECT source, status, refreshed_at, data_mode, external_subject, identity_assurance,
                  last_state, last_error_code, last_attempted_at, mapping_version
           FROM external_connections
           WHERE user_id = ?""",
        (user_id,),
    ).fetchall()
    return {row["source"]: dict(row) for row in rows}


def sync_source(
    user_id: str,
    source: str,
    subject: str | None,
    *,
    registry: Mapping[str, SourceDefinition] | None = None,
    demo_mode: bool | None = None,
) -> SourceSyncResult:
    if registry is None:
        timeout_seconds = float(current_app.config.get("DATA_SOURCE_TIMEOUT_SECONDS", 4.0))
        registry = get_source_registry(timeout_seconds=timeout_seconds)
    definition = registry.get(source)
    if definition is None:
        raise AdapterError("unsupported_source", "暂不支持此数据源。")

    active_demo_mode = current_app.config.get("DEMO_MODE", False) if demo_mode is None else demo_mode
    if definition.data_mode == "unavailable" or (definition.data_mode == "fixture" and not active_demo_mode):
        attempted_at = utc_timestamp()
        result = failed_result(
            source=definition.source_id,
            data_mode=definition.data_mode,
            identity_assurance=definition.identity_assurance,
            mapping_version=definition.mapping_version,
            attempted_at=attempted_at,
            failure=SourceFailure("unavailable", "source_disabled"),
        )
    elif definition.adapter is None:
        raise RuntimeError(f"Enabled source {source} has no adapter")
    elif definition.data_mode == "fixture":
        result = definition.adapter.fetch(user_id)
    else:
        result = definition.adapter.fetch(subject)

    _persist_result(user_id, definition, subject, result)
    return result


def _persist_result(
    user_id: str,
    definition: SourceDefinition,
    subject: str | None,
    result: SourceSyncResult,
) -> None:
    _validate_result(definition, result)
    db = get_db()
    with db:
        if result.state != "ready":
            db.execute(
                """INSERT INTO external_connections (
                       user_id, source, status, access_token, refreshed_at, data_mode,
                       external_subject, identity_assurance, last_state, last_error_code,
                       last_attempted_at, mapping_version
                   ) VALUES (?, ?, 'error', NULL, NULL, ?, NULL, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, source) DO UPDATE SET
                       last_state = excluded.last_state,
                       last_error_code = excluded.last_error_code,
                       last_attempted_at = excluded.last_attempted_at""",
                (
                    user_id,
                    result.source,
                    definition.data_mode,
                    result.identity_assurance,
                    result.state,
                    result.error_code,
                    result.attempted_at,
                    definition.mapping_version,
                ),
            )
            return

        public_subject = (subject or "").strip() if result.data_mode == "public_live" else None
        refreshed_at = result.fetched_at if result.data_mode == "public_live" else result.attempted_at
        db.execute("DELETE FROM tags WHERE user_id = ? AND source = ?", (user_id, result.source))
        for tag in result.tags:
            if tag.source != result.source or tag.data_mode != result.data_mode:
                raise RuntimeError("Adapter tag provenance does not match its result")
            db.execute(
                """INSERT INTO tags (
                       user_id, tag_id, category, name, value_json, source, verified,
                       visibility, updated_at, data_mode, evidence_kind,
                       identity_assurance, mapping_version
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    tag.tag_id,
                    tag.category,
                    tag.name,
                    json.dumps(tag.value, ensure_ascii=False, separators=(",", ":")),
                    tag.source,
                    int(tag.verified),
                    tag.visibility,
                    tag.observed_at or result.attempted_at,
                    tag.data_mode,
                    tag.evidence_kind,
                    tag.identity_assurance,
                    tag.mapping_version,
                ),
            )
        db.execute(
            """INSERT INTO external_connections (
                   user_id, source, status, access_token, refreshed_at, data_mode,
                   external_subject, identity_assurance, last_state, last_error_code,
                   last_attempted_at, mapping_version
               ) VALUES (?, ?, 'connected', NULL, ?, ?, ?, ?, 'ready', NULL, ?, ?)
               ON CONFLICT(user_id, source) DO UPDATE SET
                   status = excluded.status,
                   access_token = NULL,
                   refreshed_at = excluded.refreshed_at,
                   data_mode = excluded.data_mode,
                   external_subject = excluded.external_subject,
                   identity_assurance = excluded.identity_assurance,
                   last_state = excluded.last_state,
                   last_error_code = NULL,
                   last_attempted_at = excluded.last_attempted_at,
                   mapping_version = excluded.mapping_version""",
            (
                user_id,
                result.source,
                refreshed_at,
                result.data_mode,
                public_subject,
                result.identity_assurance,
                result.attempted_at,
                result.mapping_version,
            ),
        )


def _validate_result(definition: SourceDefinition, result: SourceSyncResult) -> None:
    if (
        result.source != definition.source_id
        or result.data_mode != definition.data_mode
        or result.identity_assurance != definition.identity_assurance
        or result.mapping_version != definition.mapping_version
    ):
        raise RuntimeError("Adapter result does not match its registry definition")
    if result.state == "ready":
        if result.error_code is not None or result.retryable:
            raise RuntimeError("Ready datasource result cannot include an error")
        if result.data_mode == "public_live" and result.fetched_at is None:
            raise RuntimeError("Public Live success requires a fetch timestamp")
        if result.data_mode == "fixture" and result.fetched_at is not None:
            raise RuntimeError("Fixture success cannot include a live fetch timestamp")
    elif result.state in {
        "unavailable",
        "timeout",
        "invalid_input",
        "malformed_response",
        "upstream_error",
    }:
        if result.error_code is None or result.fetched_at is not None or result.tags:
            raise RuntimeError("Failed datasource result has an invalid envelope")
    else:
        raise RuntimeError("Datasource result has an unknown state")

    seen_tag_ids: set[str] = set()
    for tag in result.tags:
        if (
            tag.source != result.source
            or tag.data_mode != result.data_mode
            or tag.identity_assurance != result.identity_assurance
            or tag.mapping_version != result.mapping_version
            or tag.visibility != "self_only"
            or tag.evidence_kind not in {"direct", "derived"}
            or tag.verified != (result.data_mode == "public_live")
            or (result.data_mode == "public_live" and tag.observed_at is None)
            or (result.data_mode == "fixture" and tag.observed_at is not None)
        ):
            raise RuntimeError("Adapter tag violates the normalized provenance contract")
        if tag.tag_id in seen_tag_ids:
            raise RuntimeError("Adapter returned duplicate normalized tag identifiers")
        seen_tag_ids.add(tag.tag_id)


__all__ = [
    "AdapterError",
    "DataSourceAdapter",
    "ExternalTag",
    "SourceDefinition",
    "SourceSyncResult",
    "get_source_registry",
    "source_connection_states",
    "sync_source",
]
