from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol


Clock = Callable[[], str]


@dataclass(frozen=True)
class ExternalTag:
    tag_id: str
    category: str
    name: str
    value: dict[str, object]
    source: str
    data_mode: str
    evidence_kind: str
    verified: bool
    identity_assurance: str
    visibility: str
    mapping_version: str
    observed_at: str | None


@dataclass(frozen=True)
class SourceSyncResult:
    source: str
    data_mode: str
    state: str
    identity_assurance: str
    attempted_at: str
    fetched_at: str | None
    mapping_version: str
    tags: tuple[ExternalTag, ...]
    error_code: str | None = None
    retryable: bool = False

    @property
    def error(self) -> dict[str, object] | None:
        if self.error_code is None:
            return None
        return {"code": self.error_code, "retryable": self.retryable}


class DataSourceAdapter(Protocol):
    def fetch(self, subject: str | None) -> SourceSyncResult: ...


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    label: str
    code: str
    data_mode: str
    enabled: bool
    mapping_version: str
    identity_assurance: str
    description: str
    input_label: str | None
    input_hint: str | None
    input_pattern: str | None
    input_max_length: int | None
    unavailable_reason: str | None
    adapter: DataSourceAdapter | None


class SourceFailure(RuntimeError):
    def __init__(self, state: str, code: str, *, retryable: bool = False):
        super().__init__(code)
        self.state = state
        self.code = code
        self.retryable = retryable


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_handle(subject: str | None, pattern: str, max_length: int) -> str:
    handle = (subject or "").strip()
    if not handle:
        raise SourceFailure("invalid_input", "missing_handle")
    if len(handle) > max_length or re.fullmatch(pattern, handle) is None:
        raise SourceFailure("invalid_input", "invalid_handle")
    return handle


def failed_result(
    *,
    source: str,
    data_mode: str,
    identity_assurance: str,
    mapping_version: str,
    attempted_at: str,
    failure: SourceFailure,
) -> SourceSyncResult:
    return SourceSyncResult(
        source=source,
        data_mode=data_mode,
        state=failure.state,
        identity_assurance=identity_assurance,
        attempted_at=attempted_at,
        fetched_at=None,
        mapping_version=mapping_version,
        tags=(),
        error_code=failure.code,
        retryable=failure.retryable,
    )


def make_tag(
    *,
    tag_id: str,
    category: str,
    name: str,
    value: dict[str, object],
    source: str,
    data_mode: str,
    evidence_kind: str,
    mapping_version: str,
    observed_at: str | None,
) -> ExternalTag:
    fixture = data_mode == "fixture"
    return ExternalTag(
        tag_id=tag_id,
        category=category,
        name=name,
        value=value,
        source=source,
        data_mode=data_mode,
        evidence_kind=evidence_kind,
        verified=not fixture,
        identity_assurance="synthetic_fixture" if fixture else "unverified_public_handle",
        visibility="self_only",
        mapping_version=mapping_version,
        observed_at=None if fixture else observed_at,
    )
