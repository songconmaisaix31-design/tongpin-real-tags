from __future__ import annotations

from datetime import datetime, timezone

from .models import SourceFailure


def schema_mismatch() -> SourceFailure:
    return SourceFailure("malformed_response", "schema_mismatch")


def is_non_negative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def parse_upstream_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise schema_mismatch()
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        raise schema_mismatch() from None
    if parsed.tzinfo is None:
        raise schema_mismatch()
    return parsed.astimezone(timezone.utc)
