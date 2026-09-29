#!/usr/bin/env python3
"""Interactive, credential-file-free Keep aggregate data permission probe."""

from __future__ import annotations

import getpass
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import requests

BASE_URL = "https://api.gotokeep.com"
STATS_PATH = "/pd/v3/stats/detail"
SPORT_TYPES = ("running", "cycling")
CONFIRMATION_PHRASE = "DEDICATED-TEST-ACCOUNT"
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 8
MAX_RESPONSE_BYTES = 16 * 1024
REPORT_DIR = Path(__file__).resolve().parent / "reports"


@dataclass(frozen=True)
class EnvelopeFacts:
    """Predefined booleans only; response keys and values are never retained."""

    top_level_object: bool = False
    keep_envelope_detected: bool = False
    success_flag: bool = False
    data_object_present: bool = False
    data_object_non_empty: bool = False
    auth_error_signal: bool = False
    permission_error_signal: bool = False
    response_truncated: bool = False


@dataclass(frozen=True)
class AuthenticatedProbeResult:
    probe_id: str
    method: str
    host: str
    path: str
    query_names: tuple[str, ...]
    label: str
    reason: str
    status_code: Optional[int]
    latency_ms: int
    content_type: Optional[str]
    envelope: EnvelopeFacts

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["probeId"] = result.pop("probe_id")
        result["queryNames"] = list(result.pop("query_names"))
        result["statusCode"] = result.pop("status_code")
        result["latencyMs"] = result.pop("latency_ms")
        result["contentType"] = result.pop("content_type")
        result["envelope"] = {
            "topLevelObject": self.envelope.top_level_object,
            "keepEnvelopeDetected": self.envelope.keep_envelope_detected,
            "successFlag": self.envelope.success_flag,
            "dataObjectPresent": self.envelope.data_object_present,
            "dataObjectNonEmpty": self.envelope.data_object_non_empty,
            "responseTruncated": self.envelope.response_truncated,
        }
        return result


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_cli_args(argv: Sequence[str]) -> bool:
    """Accept no runtime arguments so a secret cannot enter process arguments."""
    return len(argv) == 0


def require_private_tty() -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("Interactive terminal input is required.")


def validate_token(token: str) -> str:
    """Validate shape without logging or transforming a secret into output."""
    candidate = token
    if len(candidate) < 16 or len(candidate) > 4096:
        raise ValueError("Token length is outside the accepted range.")
    if any(character.isspace() for character in candidate):
        raise ValueError("Enter the token value only, without a Bearer prefix or whitespace.")
    return candidate


def build_session(token: str) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.clear()
    session.headers.update(
        {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "KeepAuthenticatedReadOnlyProbe/1.0",
        }
    )
    return session


def close_session(session: requests.Session) -> None:
    session.headers.pop("Authorization", None)
    session.cookies.clear()
    session.close()


def read_bounded(response: requests.Response) -> tuple[bytes, bool]:
    body = bytearray()
    limit = MAX_RESPONSE_BYTES + 1
    for chunk in response.iter_content(chunk_size=1024):
        if not chunk:
            continue
        remaining = limit - len(body)
        if remaining <= 0:
            break
        body.extend(chunk[:remaining])
        if len(body) >= limit:
            break
    truncated = len(body) > MAX_RESPONSE_BYTES
    return bytes(body[:MAX_RESPONSE_BYTES]), truncated


def inspect_envelope(raw: bytes, content_type: str, truncated: bool) -> EnvelopeFacts:
    if truncated or not raw:
        return EnvelopeFacts(response_truncated=truncated)
    if "json" not in content_type.lower() and not raw.lstrip().startswith(b"{"):
        return EnvelopeFacts()

    try:
        parsed = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return EnvelopeFacts()
    if not isinstance(parsed, dict):
        return EnvelopeFacts()

    ok_value = parsed.get("ok")
    data_value = parsed.get("data")
    error_code = parsed.get("errorCode")
    normalized_error_code = str(error_code)
    return EnvelopeFacts(
        top_level_object=True,
        keep_envelope_detected=any(key in parsed for key in ("ok", "data", "errorCode")),
        success_flag=ok_value is True,
        data_object_present=isinstance(data_value, dict),
        data_object_non_empty=isinstance(data_value, dict) and bool(data_value),
        auth_error_signal=normalized_error_code in {"401", "100010"},
        permission_error_signal=normalized_error_code == "403",
        response_truncated=False,
    )


def classify(status_code: int, facts: EnvelopeFacts) -> tuple[str, str]:
    if status_code == 401:
        return "AUTH_INVALID_OR_EXPIRED", "Keep rejected the temporary bearer token."
    if status_code == 403:
        return "PERMISSION_INSUFFICIENT", "The token was not permitted to access this route."
    if status_code in {400, 422}:
        return "REQUEST_REJECTED", "Keep rejected the fixed aggregate query contract."
    if status_code == 404:
        return "ROUTE_NOT_FOUND", "The fixed aggregate route returned 404."
    if status_code == 429:
        return "RATE_LIMITED", "Keep rate limited the read-only request."
    if 500 <= status_code <= 599:
        return "SERVICE_ERROR", "Keep returned a server-side error."
    if facts.permission_error_signal:
        return "PERMISSION_INSUFFICIENT", "The token was not permitted to access this route."
    if facts.auth_error_signal:
        return "AUTH_INVALID_OR_EXPIRED", "Keep rejected the temporary bearer token."
    if 200 <= status_code <= 299:
        if facts.success_flag and facts.data_object_present:
            return "AUTHENTICATED_AVAILABLE", "The token accessed a Keep aggregate data envelope."
        if facts.success_flag:
            return "PRIVACY_RESTRICTED", "Authentication succeeded but no data object was exposed."
        return "UNEXPECTED_RESPONSE", "The authenticated response did not match the Keep success envelope."
    return "UNEXPECTED_RESPONSE", "Keep returned an unclassified response."


def probe_sport(session: requests.Session, sport_type: str) -> AuthenticatedProbeResult:
    if sport_type not in SPORT_TYPES:
        raise ValueError("Sport type is outside the fixed allowlist.")

    started = time.perf_counter()
    facts = EnvelopeFacts()
    try:
        response = session.request(
            method="GET",
            url=f"{BASE_URL}{STATS_PATH}",
            params={"dateUnit": "all", "type": sport_type},
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            allow_redirects=False,
            stream=True,
            verify=True,
        )
        try:
            raw, truncated = read_bounded(response)
            raw_content_type = response.headers.get("Content-Type", "")
            content_type = "application/json" if "json" in raw_content_type.lower() else None
            facts = inspect_envelope(raw, content_type or "", truncated)
            label, reason = classify(response.status_code, facts)
            status_code: Optional[int] = response.status_code
        finally:
            response.close()
    except requests.exceptions.Timeout:
        label = "NETWORK_ERROR"
        reason = "The read-only request exceeded the bounded timeout."
        content_type = None
        status_code = None
    except requests.exceptions.SSLError:
        label = "NETWORK_ERROR"
        reason = "TLS verification or negotiation failed."
        content_type = None
        status_code = None
    except requests.exceptions.RequestException:
        label = "NETWORK_ERROR"
        reason = "The read-only request failed before a response was received."
        content_type = None
        status_code = None
    finally:
        session.cookies.clear()

    return AuthenticatedProbeResult(
        probe_id=f"keep.stats_detail.{sport_type}",
        method="GET",
        host="api.gotokeep.com",
        path=STATS_PATH,
        query_names=("dateUnit", "type"),
        label=label,
        reason=reason,
        status_code=status_code,
        latency_ms=round((time.perf_counter() - started) * 1000),
        content_type=content_type,
        envelope=facts,
    )


def build_report(results: list[AuthenticatedProbeResult]) -> dict[str, Any]:
    authenticated = any(result.label == "AUTHENTICATED_AVAILABLE" for result in results)
    data_non_empty = any(result.envelope.data_object_non_empty for result in results)
    return {
        "generatedAt": utc_now(),
        "platform": "keep",
        "scope": "aggregate-running-and-cycling-only",
        "credentialHandling": {
            "source": "interactive-hidden-tty-input",
            "readFromFiles": False,
            "readFromEnvironment": False,
            "acceptedViaCommandLine": False,
            "persisted": False,
            "printed": False,
        },
        "transport": {
            "tlsVerificationEnabled": True,
            "redirectsFollowed": False,
            "environmentProxiesUsed": False,
            "retries": 0,
            "maxResponseBytes": MAX_RESPONSE_BYTES,
        },
        "summary": {
            "authenticatedAggregateAccess": authenticated,
            "nonEmptyAggregateDataObserved": data_non_empty,
            "identityBindingVerified": False,
        },
        "results": [result.to_dict() for result in results],
    }


def write_report(report: dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = REPORT_DIR / f"keep-authenticated-validation-{timestamp}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


def run_interactive() -> int:
    require_private_tty()
    print("Keep authenticated read-only probe")
    print("No password, Cookie, raw response, route data, or identity value will be stored.")
    confirmation = input(
        f"Type {CONFIRMATION_PHRASE} to confirm this is a dedicated test account: "
    )
    if confirmation != CONFIRMATION_PHRASE:
        print("Cancelled: dedicated test account confirmation was not provided.")
        return 2

    token = validate_token(
        getpass.getpass("Enter the temporary Keep bearer token value (input hidden): ")
    )
    session = build_session(token)
    try:
        results = [probe_sport(session, sport_type) for sport_type in SPORT_TYPES]
    finally:
        close_session(session)
        token = ""

    report = build_report(results)
    path = write_report(report)
    print("Sanitized probe completed.")
    for result in results:
        print(f"  {result.probe_id}: {result.label}")
    print(f"Sanitized report: {path}")
    return 0 if report["summary"]["authenticatedAggregateAccess"] else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not validate_cli_args(arguments):
        print("Arguments are not accepted. Run this probe without arguments.", file=sys.stderr)
        return 2
    try:
        return run_interactive()
    except (EOFError, KeyboardInterrupt):
        print("Cancelled.", file=sys.stderr)
        return 2
    except (RuntimeError, ValueError):
        print("The secure interactive input requirements were not satisfied.", file=sys.stderr)
        return 2
    except Exception:
        print("The probe failed safely without exposing response or credential details.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
