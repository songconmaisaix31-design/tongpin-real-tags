#!/usr/bin/env python3
"""Credential-free, non-mutating availability probes for the supplied API list."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

SOURCE_ARCHIVE = r"C:\Users\DW\Downloads\All_API_Interfaces_2026-08-22.zip"
SOURCE_SHA256 = "88A3CA61F6539F82637B362510CF61D955134CF2952DC4D3D38184736F4909FF"
MAX_RESPONSE_BYTES = 4096
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 8
SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "key",
    "password",
    "secret",
    "token",
}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class Probe:
    """One documented interface and the safe action used to inspect it."""

    probe_id: str
    platform: str
    documented_method: str
    target: str
    probe_method: str
    source_ref: str
    mode: str = "http"
    json_body: Optional[Mapping[str, Any]] = None
    headers: tuple[tuple[str, str], ...] = ()
    expected_json: bool = True
    resource_scoped: bool = False
    read_only_post: bool = False
    note: str = ""


@dataclass(frozen=True)
class BodyMeta:
    """Bounded response metadata; raw response content is never retained."""

    kind: str = "empty"
    top_level_keys: tuple[str, ...] = ()
    error_code: Optional[str] = None
    auth_signal: bool = False
    rejected_signal: bool = False
    truncated: bool = False


@dataclass
class ProbeResult:
    probe_id: str
    platform: str
    documented_method: str
    probe_method: str
    target: str
    source_ref: str
    label: str
    reason: str
    status_code: Optional[int] = None
    latency_ms: Optional[int] = None
    content_type: Optional[str] = None
    body_kind: Optional[str] = None
    top_level_keys: list[str] = field(default_factory=list)
    error_code: Optional[str] = None


def _p(
    probe_id: str,
    platform: str,
    documented_method: str,
    target: str,
    probe_method: str,
    source_ref: str,
    **kwargs: Any,
) -> Probe:
    return Probe(
        probe_id=probe_id,
        platform=platform,
        documented_method=documented_method,
        target=target,
        probe_method=probe_method,
        source_ref=source_ref,
        **kwargs,
    )


PROBES: tuple[Probe, ...] = (
    _p(
        "duolingo.users",
        "Duolingo",
        "GET",
        "https://www.duolingo.com/2017-06-30/users?username=duo",
        "GET",
        "DataSourceAdapter_Interface.md:203-230; adapters/duolingo_adapter.py:24-39",
        note="Concrete workspace implementation for an adapter whose archive contract omits the path.",
    ),
    _p(
        "leetcode.cn.graphql",
        "LeetCode CN",
        "POST",
        "https://leetcode.cn/graphql",
        "POST",
        "DataSourceAdapter_Interface.md:16; adapters/leetcode_adapter.py:60-84",
        json_body={"query": "query AvailabilityProbe { __typename }"},
        headers=(("Origin", "https://leetcode.cn"), ("Referer", "https://leetcode.cn/")),
        read_only_post=True,
        note="Read-only GraphQL query; the archive declares LeetCode but provides no endpoint.",
    ),
    _p(
        "leetcode.com.graphql",
        "LeetCode COM",
        "POST",
        "https://leetcode.com/graphql",
        "POST",
        "DataSourceAdapter_Interface.md:16; adapters/leetcode_adapter.py:60-84",
        json_body={"query": "query AvailabilityProbe { __typename }"},
        headers=(("Origin", "https://leetcode.com"), ("Referer", "https://leetcode.com/")),
        read_only_post=True,
        note="Read-only GraphQL query; the archive declares LeetCode but provides no endpoint.",
    ),
    _p(
        "keep.login",
        "Keep",
        "POST",
        "https://api.gotokeep.com/v1.1/users/login",
        "OPTIONS",
        "Keep_API_Integration_Example.py:24,61-103",
        note="Authentication operation is not executed.",
    ),
    _p(
        "keep.stats_detail",
        "Keep",
        "GET",
        "https://api.gotokeep.com/pd/v3/stats/detail?dateUnit=all&type=running",
        "GET",
        "Keep_API_Integration_Example.py:25,105-135",
    ),
    _p(
        "keep.stats_records",
        "Keep",
        "GET",
        "https://api.gotokeep.com/pd/v3/stats/records?page=1&limit=1&type=running",
        "GET",
        "Keep_API_Integration_Example.py:26,137-166",
    ),
    _p(
        "keep.running_log",
        "Keep",
        "GET",
        "https://api.gotokeep.com/pd/v3/runninglog/0",
        "GET",
        "Keep_API_Integration_Example.py:27,168-190",
        resource_scoped=True,
    ),
    _p(
        "keep.cycling_log",
        "Keep",
        "GET",
        "https://api.gotokeep.com/pd/v3/cyclinglog/0",
        "GET",
        "Keep_API_Integration_Example.py:28,172-190",
        resource_scoped=True,
    ),
    _p(
        "steam.resolve_vanity",
        "Steam",
        "GET",
        "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?vanityurl=valve",
        "GET",
        "V2_DataSources_Full_Research.md:44-48",
    ),
    _p(
        "steam.player_summaries",
        "Steam",
        "GET",
        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?steamids=0",
        "GET",
        "V2_DataSources_Full_Research.md:51-88",
    ),
    _p(
        "steam.owned_games",
        "Steam",
        "GET",
        "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?steamid=0&include_appinfo=1&include_played_free_games=1",
        "GET",
        "V2_DataSources_Full_Research.md:90-132",
    ),
    _p(
        "steam.recent_games",
        "Steam",
        "GET",
        "https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/?steamid=0&count=1",
        "GET",
        "V2_DataSources_Full_Research.md:134-145",
    ),
    _p(
        "steam.level",
        "Steam",
        "GET",
        "https://api.steampowered.com/IPlayerService/GetSteamLevel/v1/?steamid=0",
        "GET",
        "V2_DataSources_Full_Research.md:147-153",
    ),
    _p(
        "steam.badges",
        "Steam",
        "GET",
        "https://api.steampowered.com/IPlayerService/GetBadges/v1/?steamid=0",
        "GET",
        "V2_DataSources_Full_Research.md:154-183",
    ),
    _p(
        "steam.achievements",
        "Steam",
        "GET",
        "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/?steamid=0&appid=730",
        "GET",
        "V2_DataSources_Full_Research.md:185-197",
    ),
    _p(
        "github.user",
        "GitHub",
        "GET",
        "https://api.github.com/users/octocat",
        "GET",
        "V2_DataSources_Full_Research.md:377-424",
    ),
    _p(
        "github.repos",
        "GitHub",
        "GET",
        "https://api.github.com/users/octocat/repos?sort=updated&type=owner&per_page=1",
        "GET",
        "V2_DataSources_Full_Research.md:426-442",
    ),
    _p(
        "github.events",
        "GitHub",
        "GET",
        "https://api.github.com/users/octocat/events?per_page=1",
        "GET",
        "V2_DataSources_Full_Research.md:444-461",
    ),
    _p(
        "github.graphql",
        "GitHub",
        "POST",
        "https://api.github.com/graphql",
        "POST",
        "V2_DataSources_Full_Research.md:463-520",
        json_body={"query": "query AvailabilityProbe { __typename }"},
        read_only_post=True,
    ),
    _p(
        "netease.login_cellphone",
        "NetEase Cloud Music local service",
        "POST",
        "http://localhost:3000/login/cellphone",
        "OPTIONS",
        "V2_DataSources_Full_Research.md:731-739",
        note="Login is not executed.",
    ),
    _p(
        "netease.qr_key",
        "NetEase Cloud Music local service",
        "POST",
        "http://localhost:3000/login/qr/key",
        "OPTIONS",
        "V2_DataSources_Full_Research.md:741-743",
        note="QR login session creation is not executed.",
    ),
    _p(
        "netease.qr_create",
        "NetEase Cloud Music local service",
        "POST",
        "http://localhost:3000/login/qr/create?key=synthetic&qrimg=true",
        "OPTIONS",
        "V2_DataSources_Full_Research.md:744",
        note="QR creation is not executed.",
    ),
    _p(
        "netease.qr_check_invalid_port",
        "NetEase Cloud Music local service",
        "POST",
        "http://localhost:300300/login/qr/check?key=synthetic",
        "NOT_EXECUTED",
        "V2_DataSources_Full_Research.md:745-746",
        mode="invalid",
        note="Port 300300 exceeds the valid TCP port range.",
    ),
    _p(
        "netease.user_detail",
        "NetEase Cloud Music local service",
        "POST",
        "http://localhost:3000/user/detail?uid=0",
        "OPTIONS",
        "V2_DataSources_Full_Research.md:753-758",
    ),
    _p(
        "netease.user_record",
        "NetEase Cloud Music local service",
        "POST",
        "http://localhost:3000/user/record?uid=0&type=1",
        "OPTIONS",
        "V2_DataSources_Full_Research.md:796-805",
    ),
    _p(
        "netease.user_playlist",
        "NetEase Cloud Music local service",
        "POST",
        "http://localhost:3000/user/playlist?uid=0&limit=1",
        "OPTIONS",
        "V2_DataSources_Full_Research.md:851-856",
    ),
    _p(
        "netease.daily_checkin",
        "NetEase Cloud Music local service",
        "POST",
        "http://localhost:3000/daily_checkin?type=0",
        "OPTIONS",
        "V2_DataSources_Full_Research.md:862-867",
        note="State-changing check-in is not executed.",
    ),
    _p(
        "netease.user_level",
        "NetEase Cloud Music local service",
        "POST",
        "http://localhost:3000/user/level?uid=0",
        "OPTIONS",
        "V2_DataSources_Full_Research.md:869-871",
    ),
    _p(
        "weread.mcp_reading_stats",
        "WeRead MCP",
        "MCP_TOOL",
        "mcp://weread/weread_reading_stats",
        "NOT_EXECUTED",
        "V2_DataSources_Full_Research.md:1095-1138",
        mode="mcp",
        note="No configured WeRead MCP server is in scope.",
    ),
    _p(
        "weread.mcp_shelf",
        "WeRead MCP",
        "MCP_TOOL",
        "mcp://weread/weread_shelf",
        "NOT_EXECUTED",
        "V2_DataSources_Full_Research.md:1140-1158",
        mode="mcp",
        note="No configured WeRead MCP server is in scope.",
    ),
    _p(
        "weread.mcp_notes",
        "WeRead MCP",
        "MCP_TOOL",
        "mcp://weread/weread_notes",
        "NOT_EXECUTED",
        "V2_DataSources_Full_Research.md:1160-1176",
        mode="mcp",
        note="No configured WeRead MCP server is in scope.",
    ),
    _p(
        "weread.local_reading_stats",
        "WeRead assumed local HTTP",
        "GET",
        "http://localhost:3001/reading/stats",
        "GET",
        "V2_DataSources_Full_Research.md:1197-1213",
        note="Example-code assumption, not an MCP transport contract.",
    ),
    _p(
        "weread.local_shelf",
        "WeRead assumed local HTTP",
        "GET",
        "http://localhost:3001/shelf?limit=1",
        "GET",
        "V2_DataSources_Full_Research.md:1215-1229",
        note="Example-code assumption, not an MCP transport contract.",
    ),
    _p(
        "weread.local_notes",
        "WeRead assumed local HTTP",
        "GET",
        "http://localhost:3001/notes",
        "GET",
        "V2_DataSources_Full_Research.md:1231-1247",
        note="Example-code assumption, not an MCP transport contract.",
    ),
    _p(
        "weread.internal_reading_stats",
        "WeRead internal API",
        "GET",
        "https://i.weread.qq.com/user/reading/statistics",
        "GET",
        "V2_DataSources_Full_Research.md:1204-1213",
    ),
    _p(
        "weread.internal_shelf",
        "WeRead internal API",
        "GET",
        "https://i.weread.qq.com/shelf/sync?limit=1",
        "GET",
        "V2_DataSources_Full_Research.md:1215-1229",
    ),
    _p(
        "weread.internal_notes",
        "WeRead internal API",
        "GET",
        "https://i.weread.qq.com/note/getList",
        "GET",
        "V2_DataSources_Full_Research.md:1231-1247",
    ),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sanitize_target(target: str) -> str:
    """Redact userinfo and sensitive query values without logging raw secrets."""
    try:
        parts = urlsplit(target)
        if parts.scheme == "mcp":
            return target
        host = parts.hostname or ""
        port = parts.port
        netloc = host if port is None else f"{host}:{port}"
        query = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            safe_value = "[REDACTED]" if key.lower() in SENSITIVE_QUERY_KEYS else value
            query.append((key, safe_value))
        return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), ""))
    except ValueError:
        return "<invalid-target>"


def validate_target(probe: Probe) -> Optional[str]:
    if probe.mode == "mcp":
        return None
    if probe.mode == "invalid":
        return probe.note or "The documented target is invalid."
    if probe.probe_method not in SAFE_METHODS:
        if probe.probe_method != "POST" or not probe.read_only_post:
            return "The configured probe action violates the non-mutating safety policy."
        query = str((probe.json_body or {}).get("query", "")).lstrip().lower()
        if not query.startswith("query"):
            return "Only an explicit read-only GraphQL query may use POST."
    if any(key.lower() in {"authorization", "cookie"} for key, _ in probe.headers):
        return "Probe contracts must not include authentication headers."
    try:
        parts = urlsplit(probe.target)
        _ = parts.port
    except ValueError:
        return "The documented port is outside the valid range."
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return "The documented target is not a valid HTTP(S) URL."
    if parts.username or parts.password:
        return "Credentials embedded in URLs are not allowed."
    return None


def _bounded_body(response: requests.Response) -> tuple[bytes, bool]:
    data = bytearray()
    for chunk in response.iter_content(chunk_size=1024):
        if not chunk:
            continue
        remaining = (MAX_RESPONSE_BYTES + 1) - len(data)
        if remaining <= 0:
            break
        data.extend(chunk[:remaining])
        if len(data) > MAX_RESPONSE_BYTES:
            break
    truncated = len(data) > MAX_RESPONSE_BYTES
    return bytes(data[:MAX_RESPONSE_BYTES]), truncated


def _safe_key(value: Any) -> Optional[str]:
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9_.:-]{1,40}", text):
        return text
    return None


def summarize_body(raw: bytes, content_type: str, truncated: bool = False) -> BodyMeta:
    if not raw:
        return BodyMeta(truncated=truncated)

    parsed: Any = None
    if "json" in content_type.lower() or raw.lstrip().startswith((b"{", b"[")):
        try:
            parsed = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = None

    if isinstance(parsed, dict):
        keys = tuple(
            key
            for key in sorted((_safe_key(k) for k in parsed), key=lambda x: x or "")
            if key is not None
        )[:20]
        code_value = None
        for candidate in ("errorCode", "errcode", "code"):
            if candidate in parsed:
                code_value = _safe_key(parsed[candidate])
                break

        messages: list[str] = []
        for candidate in ("message", "text", "errmsg", "error"):
            value = parsed.get(candidate)
            if isinstance(value, str):
                messages.append(value.lower())
        errors = parsed.get("errors")
        if isinstance(errors, list):
            for error in errors[:2]:
                if isinstance(error, dict) and isinstance(error.get("message"), str):
                    messages.append(error["message"].lower())

        joined = " ".join(messages)
        auth_signal = any(
            marker in joined
            for marker in ("auth", "credential", "cookie", "login", "password", "token", "unauthorized")
        )
        if parsed.get("ok") is False and code_value in {"100010", "401", "403"}:
            auth_signal = True
        if "errcode" in parsed and str(parsed.get("errcode")) not in {"0", "200", "None"}:
            auth_signal = True
        rejected_signal = bool(errors) or parsed.get("ok") is False
        if "code" in parsed and str(parsed.get("code")) not in {"0", "200", "None"}:
            rejected_signal = True
        return BodyMeta(
            kind="object",
            top_level_keys=keys,
            error_code=code_value,
            auth_signal=auth_signal,
            rejected_signal=rejected_signal,
            truncated=truncated,
        )
    if isinstance(parsed, list):
        return BodyMeta(kind="list", truncated=truncated)
    if truncated and "json" in content_type.lower():
        first = raw.lstrip()[:1]
        if first == b"{":
            return BodyMeta(kind="object_truncated", truncated=True)
        if first == b"[":
            return BodyMeta(kind="list_truncated", truncated=True)
    return BodyMeta(kind="text", truncated=truncated)


def classify_response(probe: Probe, status: int, body: BodyMeta) -> tuple[str, str]:
    if status in {401, 403} or body.auth_signal:
        return "AUTH_REQUIRED", "The route responded but requires valid authentication."
    if status in {400, 422}:
        return "REQUEST_REJECTED", "The route rejected the synthetic or incomplete input."
    if status == 404:
        if probe.resource_scoped:
            return "RESOURCE_NOT_FOUND", "The synthetic resource was not found; the route may still exist."
        return "ROUTE_NOT_FOUND", "The documented path returned 404."
    if status == 405:
        return "METHOD_NOT_ALLOWED", "The safe probe method is not supported."
    if status == 429:
        return "RATE_LIMITED", "The service is reachable but currently rate limited."
    if 500 <= status <= 599:
        return "SERVICE_ERROR", "The service returned a server-side error."
    if 200 <= status <= 299:
        if probe.probe_method in {"HEAD", "OPTIONS"}:
            return "INCONCLUSIVE_SAFE_PROBE", "The safe handshake succeeded; business behavior was not executed."
        if body.rejected_signal:
            return "REQUEST_REJECTED", "The HTTP request succeeded but the API rejected the operation."
        if probe.expected_json and body.kind not in {
            "object",
            "list",
            "object_truncated",
            "list_truncated",
        }:
            return "UNEXPECTED_RESPONSE", "The route did not return the expected JSON response shape."
        return "AVAILABLE", "The safe functional request returned the expected response shape."
    if 300 <= status <= 399:
        return "UNEXPECTED_RESPONSE", "The service redirected the request; redirects were not followed."
    return "UNEXPECTED_RESPONSE", "The route returned an unclassified HTTP response."


def _is_local_target(target: str) -> bool:
    try:
        return (urlsplit(target).hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}
    except ValueError:
        return False


def probe_one(session: requests.Session, probe: Probe) -> ProbeResult:
    target = sanitize_target(probe.target)
    if probe.mode == "mcp":
        return ProbeResult(
            probe.probe_id,
            probe.platform,
            probe.documented_method,
            probe.probe_method,
            target,
            probe.source_ref,
            "NOT_TESTED_PREREQUISITE",
            probe.note or "A configured MCP server is required.",
        )

    invalid_reason = validate_target(probe)
    if invalid_reason:
        return ProbeResult(
            probe.probe_id,
            probe.platform,
            probe.documented_method,
            probe.probe_method,
            target,
            probe.source_ref,
            "CONTRACT_INVALID",
            invalid_reason,
        )

    headers = {
        "Accept": "application/json",
        "User-Agent": "APIAvailabilityProbe/1.0",
    }
    headers.update(dict(probe.headers))
    if probe.json_body is not None:
        headers["Content-Type"] = "application/json"

    started = time.perf_counter()
    try:
        response = session.request(
            method=probe.probe_method,
            url=probe.target,
            headers=headers,
            json=probe.json_body,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            allow_redirects=False,
            stream=True,
        )
        try:
            raw, truncated = _bounded_body(response)
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip()[:80]
            body = summarize_body(raw, content_type, truncated)
            label, reason = classify_response(probe, response.status_code, body)
            return ProbeResult(
                probe.probe_id,
                probe.platform,
                probe.documented_method,
                probe.probe_method,
                target,
                probe.source_ref,
                label,
                reason,
                status_code=response.status_code,
                latency_ms=round((time.perf_counter() - started) * 1000),
                content_type=content_type or None,
                body_kind=body.kind,
                top_level_keys=list(body.top_level_keys),
                error_code=body.error_code,
            )
        finally:
            response.close()
    except (requests.exceptions.InvalidURL, requests.exceptions.MissingSchema):
        label = "CONTRACT_INVALID"
        reason = "The HTTP client rejected the documented URL."
    except requests.exceptions.Timeout:
        label = "NETWORK_ERROR"
        reason = "The request exceeded the bounded timeout."
    except requests.exceptions.SSLError:
        label = "NETWORK_ERROR"
        reason = "TLS verification or negotiation failed."
    except requests.exceptions.ConnectionError:
        if _is_local_target(probe.target):
            label = "PREREQUISITE_MISSING"
            reason = "The required local service is not listening."
        else:
            label = "NETWORK_ERROR"
            reason = "The remote connection failed."
    except requests.exceptions.RequestException:
        label = "NETWORK_ERROR"
        reason = "The HTTP request failed before a response was received."

    return ProbeResult(
        probe.probe_id,
        probe.platform,
        probe.documented_method,
        probe.probe_method,
        target,
        probe.source_ref,
        label,
        reason,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )


def build_sessions() -> tuple[requests.Session, requests.Session]:
    """Use environment networking remotely, but never proxy localhost probes."""
    remote_session = requests.Session()
    remote_session.headers.clear()
    local_session = requests.Session()
    local_session.headers.clear()
    local_session.trust_env = False
    return remote_session, local_session


def run_all(probes: tuple[Probe, ...] = PROBES) -> list[ProbeResult]:
    remote_session, local_session = build_sessions()
    try:
        return [
            probe_one(local_session if _is_local_target(probe.target) else remote_session, probe)
            for probe in probes
        ]
    finally:
        local_session.close()
        remote_session.close()


def build_payload(results: list[ProbeResult]) -> dict[str, Any]:
    counts = Counter(result.label for result in results)
    return {
        "generatedAt": utc_now(),
        "sourceArchive": SOURCE_ARCHIVE,
        "sourceSha256": SOURCE_SHA256,
        "safety": {
            "credentialsRead": False,
            "redirectsFollowed": False,
            "tlsVerificationDisabled": False,
            "rawBodiesStored": False,
            "maxResponseBytes": MAX_RESPONSE_BYTES,
        },
        "summary": {"total": len(results), "byLabel": dict(sorted(counts.items()))},
        "results": [asdict(result) for result in results],
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# API Interface Availability Validation",
        "",
        f"- Generated: `{payload['generatedAt']}`",
        f"- Source SHA-256: `{payload['sourceSha256']}`",
        f"- Interfaces: `{summary['total']}`",
        "- Credentials read: `false`",
        "- Raw response bodies stored: `false`",
        "- Redirects followed: `false`",
        "- TLS verification: `enabled`",
        "",
        "## Summary",
        "",
        "| Label | Count |",
        "|---|---:|",
    ]
    for label, count in summary["byLabel"].items():
        lines.append(f"| `{label}` | {count} |")

    lines.extend(
        [
            "",
            "## Results",
            "",
            "| Platform | Contract ID | Documented | Probe | HTTP | Latency | Result |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for result in payload["results"]:
        status = "-" if result["status_code"] is None else str(result["status_code"])
        latency = "-" if result["latency_ms"] is None else f"{result['latency_ms']} ms"
        lines.append(
            f"| {result['platform']} | `{result['probe_id']}` | "
            f"`{result['documented_method']}` | `{result['probe_method']}` | "
            f"{status} | {latency} | `{result['label']}` |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `AVAILABLE` means a safe request succeeded with the expected response shape.",
            "- `AUTH_REQUIRED` proves route reachability, not authenticated business success.",
            "- `INCONCLUSIVE_SAFE_PROBE` means only a non-mutating handshake was executed.",
            "- `PREREQUISITE_MISSING` means the documented local service was not running.",
            "- MCP tools require a configured MCP server and are not equivalent to local HTTP paths.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(path: str, content: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", metavar="PATH", help="Write sanitized JSON results.")
    parser.add_argument("--markdown", metavar="PATH", help="Write a Markdown summary.")
    parser.add_argument(
        "--platform",
        action="append",
        help="Probe only matching platform names; may be repeated.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    probes = PROBES
    if args.platform:
        wanted = {value.lower() for value in args.platform}
        probes = tuple(probe for probe in PROBES if probe.platform.lower() in wanted)
        if not probes:
            print("No probes matched the requested platform.", file=sys.stderr)
            return 2

    results = run_all(probes)
    payload = build_payload(results)
    if args.json:
        write_report(args.json, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    if args.markdown:
        write_report(args.markdown, render_markdown(payload))

    counts = payload["summary"]["byLabel"]
    print(f"Probed {len(results)} interfaces without reading credentials.")
    for label, count in counts.items():
        print(f"  {label}: {count}")
    for result in results:
        status = "-" if result.status_code is None else str(result.status_code)
        print(f"  {result.probe_id:<36} {status:>3} {result.label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
