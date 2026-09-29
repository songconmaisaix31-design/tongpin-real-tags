from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from http.client import HTTPException
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener

from flask import current_app, has_request_context, request


SYSTEM_PROMPT = (
    "你是 RealTags 的 AI 候场搭子，不是真人匹配对象。"
    "使用简体中文友善互动，每次不超过 120 字，最多问一个问题。"
    "不得声称拥有真实身份、年龄、性别、住址、职业、现实经历或联系方式，"
    "不得邀请线下见面，也不得暗示用户已经匹配到真人。"
)
USER_AGENT = "RealTags-AI-Standby/1.0"
MAX_CONTEXT_TURNS = 12
MAX_RESPONSE_BYTES = 64 * 1024
MAX_REPLY_CHARS = 500
VERCEL_AI_GATEWAY_COMPLETION_URL = "https://ai-gateway.vercel.sh/v1/chat/completions"


class AiFallbackFailure(RuntimeError):
    """Expose a bounded failure code without retaining an upstream body."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CompletionRequest:
    url: str
    api_key: str
    model: str
    messages: tuple[tuple[str, str], ...]
    timeout_seconds: float
    max_bytes: int = MAX_RESPONSE_BYTES


class CompletionTransport(Protocol):
    def __call__(self, request: CompletionRequest) -> str: ...


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = build_opener(NoRedirectHandler())


def _completion_url(base_url: str) -> str:
    try:
        parsed = urlsplit(base_url.strip())
        _ = parsed.port
    except ValueError as error:
        raise AiFallbackFailure("invalid_configuration") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise AiFallbackFailure("invalid_configuration")
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", parsed.netloc, f"{path}/chat/completions", "", ""))


def _configured_bearer_token(base_url: str) -> str:
    completion_url = _completion_url(base_url)
    api_key = current_app.config.get("AI_FALLBACK_API_KEY")
    if isinstance(api_key, str) and api_key.strip():
        return api_key.strip()

    # Vercel injects the renewable runtime token into each Function request.
    # The config fallback exists only for builds, local verification, and tests.
    oidc_token = request.headers.get("x-vercel-oidc-token", "") if has_request_context() else ""
    if not oidc_token:
        oidc_token = current_app.config.get("AI_FALLBACK_OIDC_TOKEN")
    if (
        completion_url == VERCEL_AI_GATEWAY_COMPLETION_URL
        and isinstance(oidc_token, str)
        and oidc_token.strip()
    ):
        return oidc_token.strip()
    raise AiFallbackFailure("not_configured")


def ai_fallback_available() -> bool:
    if not current_app.config.get("AI_FALLBACK_ENABLED", False):
        return False
    base_url = current_app.config.get("AI_FALLBACK_BASE_URL")
    model = current_app.config.get("AI_FALLBACK_MODEL")
    if not all(isinstance(value, str) and value.strip() for value in (base_url, model)):
        return False
    try:
        _configured_bearer_token(base_url)
    except AiFallbackFailure:
        return False
    return True


def _configured_request(messages: list[tuple[str, str]]) -> CompletionRequest:
    if not ai_fallback_available():
        raise AiFallbackFailure("not_configured")
    bounded_messages = []
    for role, content in messages:
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        text = content.strip()
        if text:
            bounded_messages.append((role, text[:MAX_REPLY_CHARS]))
    bounded_messages = bounded_messages[-MAX_CONTEXT_TURNS:]
    if not bounded_messages or bounded_messages[-1][0] != "user":
        raise AiFallbackFailure("invalid_context")
    return CompletionRequest(
        url=_completion_url(current_app.config["AI_FALLBACK_BASE_URL"]),
        api_key=_configured_bearer_token(current_app.config["AI_FALLBACK_BASE_URL"]),
        model=current_app.config["AI_FALLBACK_MODEL"].strip(),
        messages=tuple(bounded_messages),
        timeout_seconds=float(current_app.config.get("AI_FALLBACK_TIMEOUT_SECONDS", 8.0)),
    )


def _bounded_reply_text(content: object) -> str:
    if not isinstance(content, str) or not content.strip():
        raise AiFallbackFailure("invalid_response")
    reply = content.strip()
    if len(reply) > MAX_REPLY_CHARS:
        reply = f"{reply[: MAX_REPLY_CHARS - 1].rstrip()}…"
    return reply


def _bounded_reply(payload: object) -> str:
    if not isinstance(payload, dict):
        raise AiFallbackFailure("invalid_response")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise AiFallbackFailure("invalid_response")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return _bounded_reply_text(content)


def request_chat_completion(
    request: CompletionRequest,
    *,
    opener: OpenerDirector | None = None,
) -> str:
    body = json.dumps(
        {
            "model": request.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                *({"role": role, "content": content} for role, content in request.messages),
            ],
            "temperature": 0.8,
            "max_tokens": 180,
            "stream": False,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    upstream_request = Request(
        request.url,
        data=body,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {request.api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with (opener or _OPENER).open(upstream_request, timeout=request.timeout_seconds) as response:
            raw = response.read(request.max_bytes + 1)
    except HTTPError as error:
        if 300 <= error.code < 400:
            code = "redirect_rejected"
        elif error.code == 401:
            code = "authentication_failed"
        elif error.code == 403:
            code = "permission_denied"
        elif error.code == 429:
            code = "rate_limited"
        elif 400 <= error.code < 500:
            code = "request_rejected"
        else:
            code = "upstream_error"
        raise AiFallbackFailure(code) from None
    except (socket.timeout, TimeoutError):
        raise AiFallbackFailure("timeout") from None
    except URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise AiFallbackFailure("timeout") from None
        raise AiFallbackFailure("network_error") from None
    except (HTTPException, OSError):
        raise AiFallbackFailure("network_error") from None

    if len(raw) > request.max_bytes:
        raise AiFallbackFailure("response_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AiFallbackFailure("invalid_response") from None
    return _bounded_reply(payload)


def complete_ai_reply(
    messages: list[tuple[str, str]],
    *,
    transport: CompletionTransport | None = None,
) -> str:
    request = _configured_request(messages)
    configured_transport = current_app.config.get("AI_FALLBACK_TRANSPORT")
    selected_transport = transport or (configured_transport if callable(configured_transport) else None)
    return _bounded_reply_text((selected_transport or request_chat_completion)(request))
