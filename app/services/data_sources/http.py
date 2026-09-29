from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from email.message import Message
from http.client import HTTPException
from typing import Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener

from .models import SourceFailure


USER_AGENT = "RealTags-Hackathon/1.0"


@dataclass(frozen=True)
class JsonRequest:
    method: str
    url: str
    timeout_seconds: float
    max_bytes: int
    body: bytes | None = None
    headers: tuple[tuple[str, str], ...] = ()


class JsonTransport(Protocol):
    def __call__(self, request: JsonRequest) -> object: ...


class ResponseLike(Protocol):
    headers: Message | Mapping[str, str]

    def __enter__(self) -> ResponseLike: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...

    def read(self, amount: int = -1) -> bytes: ...


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = build_opener(NoRedirectHandler())


def _header(headers: Message | Mapping[str, str] | None, name: str) -> str | None:
    if headers is None:
        return None
    value = headers.get(name)
    if value is not None or isinstance(headers, Message):
        return value
    lowered_name = name.lower()
    return next((item for key, item in headers.items() if key.lower() == lowered_name), None)


def _http_failure(status: int, headers: Message | Mapping[str, str] | None) -> SourceFailure:
    if 300 <= status < 400:
        return SourceFailure("upstream_error", "redirect_rejected")
    if status == 404:
        return SourceFailure("unavailable", "profile_not_found")
    if status == 429 or (status == 403 and _header(headers, "X-RateLimit-Remaining") == "0"):
        return SourceFailure("upstream_error", "rate_limited", retryable=True)
    if 400 <= status < 500:
        return SourceFailure("upstream_error", "http_4xx")
    return SourceFailure("upstream_error", "http_5xx", retryable=True)


def request_json(request: JsonRequest, *, opener: OpenerDirector | None = None) -> object:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    headers.update(dict(request.headers))
    if any(name.lower() in {"authorization", "cookie"} for name in headers):
        raise ValueError("Credential headers are not permitted for public datasource requests")

    upstream_request = Request(
        request.url,
        data=request.body,
        headers=headers,
        method=request.method,
    )
    try:
        with (opener or _OPENER).open(upstream_request, timeout=request.timeout_seconds) as response:
            content_length = _header(response.headers, "Content-Length")
            if content_length is not None:
                try:
                    if int(content_length) > request.max_bytes:
                        raise SourceFailure("malformed_response", "response_too_large")
                except ValueError:
                    pass
            raw = response.read(request.max_bytes + 1)
    except SourceFailure:
        raise
    except HTTPError as error:
        raise _http_failure(error.code, error.headers) from None
    except (socket.timeout, TimeoutError):
        raise SourceFailure("timeout", "request_timeout", retryable=True) from None
    except URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise SourceFailure("timeout", "request_timeout", retryable=True) from None
        raise SourceFailure("upstream_error", "network_error", retryable=True) from None
    except (HTTPException, OSError):
        raise SourceFailure("upstream_error", "network_error", retryable=True) from None

    if len(raw) > request.max_bytes:
        raise SourceFailure("malformed_response", "response_too_large")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SourceFailure("malformed_response", "invalid_json") from None
