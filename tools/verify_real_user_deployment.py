from __future__ import annotations

import argparse
import http.cookiejar
import ipaddress
import re
import secrets
import socket
from contextlib import contextmanager
from dataclasses import dataclass
from html import unescape
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener


MAX_RESPONSE_BYTES = 1 * 1024 * 1024


@dataclass(frozen=True)
class QaUser:
    email: str
    password: str
    alias: str


@dataclass(frozen=True)
class HttpResult:
    status: int
    url: str
    text: str


@contextmanager
def pinned_dns(hostname: str, edge_ip: str):
    """Pin one hostname to a reviewed edge while preserving TLS hostname checks."""
    original = socket.getaddrinfo

    def resolve(host: str, port: int, *args, **kwargs):
        target = edge_ip if host == hostname else host
        return original(target, port, *args, **kwargs)

    socket.getaddrinfo = resolve
    try:
        yield
    finally:
        socket.getaddrinfo = original


class HttpClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout_seconds = timeout_seconds
        self.cookies = http.cookiejar.CookieJar()
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(self.cookies))

    def request(
        self,
        path: str,
        *,
        form: dict[str, str | list[str]] | None = None,
        expected_status: int = 200,
    ) -> HttpResult:
        data = urlencode(form, doseq=True).encode("utf-8") if form is not None else None
        request = Request(
            urljoin(self.base_url, path.lstrip("/")),
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "RealTags-Release-Check/1.0",
            },
        )
        try:
            response = self.opener.open(request, timeout=self.timeout_seconds)
        except HTTPError as error:
            if error.code != expected_status:
                raise RuntimeError(f"{path} returned HTTP {error.code}, expected {expected_status}") from error
            body = error.read(MAX_RESPONSE_BYTES + 1)
            final_url = error.geturl()
            status = error.code
        else:
            with response:
                status = response.status
                final_url = response.geturl()
                body = response.read(MAX_RESPONSE_BYTES + 1)
        if status != expected_status:
            raise RuntimeError(f"{path} returned HTTP {status}, expected {expected_status}")
        if len(body) > MAX_RESPONSE_BYTES:
            raise RuntimeError(f"{path} exceeded the bounded response size")
        return HttpResult(status=status, url=final_url, text=body.decode("utf-8", errors="replace"))


def registration_form(user: QaUser) -> dict[str, str | list[str]]:
    return {
        "email": user.email,
        "password": user.password,
        "anonymous_alias": user.alias,
        "birth_year": "1998",
        "gender": "male",
        "match_gender": "male",
        "city": "北京",
        "purposes": ["随便聊聊"],
        "interests": ["游戏", "宠物"],
        "mbti": "INTJ",
        "zodiac": "天秤",
        "schedule": "夜猫子",
    }


def register(client: HttpClient, user: QaUser) -> None:
    result = client.request("/register", form=registration_form(user))
    if urlparse(result.url).path != "/profile/connections":
        raise RuntimeError("Registration did not auto-login and reach the connection page")
    if "注册成功，已自动登录" not in result.text or "Fixture 演示标签" in result.text:
        raise RuntimeError("Registration did not preserve the real-user boundary")
    profile = client.request("/profile").text
    for expected in (user.alias, "北京", "INTJ", "夜猫子"):
        if expected not in profile:
            raise RuntimeError("A submitted registration field is missing from the profile")


def login(client: HttpClient, user: QaUser) -> None:
    result = client.request(
        "/login",
        form={"email": user.email, "password": user.password},
    )
    if urlparse(result.url).path != "/profile" or user.alias not in result.text:
        raise RuntimeError("A persisted QA account could not log in")


def sync_public_sources(client: HttpClient) -> list[str]:
    handles = {
        "duolingo": "duolingo",
        "github": "octocat",
        "leetcode_com": "neal_wu",
    }
    states = []
    for source, handle in handles.items():
        result = client.request(
            f"/profile/connections/{source}/sync",
            form={"external_handle": handle},
        )
        if "flash-success" in result.text and "已同步" in result.text:
            states.append(f"{source}=ready")
        elif "flash-error" in result.text:
            states.append(f"{source}=explicit_failure")
        else:
            raise RuntimeError(f"{source} did not expose a bounded sync state")
    client.request("/profile/connections/keep/sync", form={}, expected_status=404)
    connections = client.request("/profile/connections").text
    if "演示模式已关闭，本次运行不载入 Fixture" not in connections:
        raise RuntimeError("Keep did not remain unavailable in real-user mode")
    return states


def hidden_value(html: str, name: str) -> str:
    match = re.search(rf'name="{re.escape(name)}" value="([^"]+)"', html)
    if not match:
        raise RuntimeError(f"Missing hidden form value: {name}")
    return unescape(match.group(1))


def start_conversation(client: HttpClient) -> str:
    searching = client.request("/matches/search/start", form={})
    if urlparse(searching.url).path != "/matches/searching":
        raise RuntimeError("The online match search did not start")
    attempt_id = hidden_value(searching.text, "attempt_id")
    result = client.request(
        "/matches/search/complete",
        form={"attempt_id": attempt_id},
    )
    action = re.search(r'<form method="post" action="(/matches/[^\"]+/start)">', result.text)
    if not action:
        raise RuntimeError("The match result did not expose the anonymous start action")
    started = client.request(action.group(1), form={"attempt_id": attempt_id})
    match = re.fullmatch(r"/conversations/([^/]+)", urlparse(started.url).path)
    if not match:
        raise RuntimeError("The online match did not create a direct conversation")
    return match.group(1)


def verify_chat_and_safety(
    first: HttpClient,
    second: HttpClient,
    conversation_id: str,
) -> None:
    first_message = "线上持久化核验：第一条消息"
    second_message = "线上持久化核验：第二条回复"
    first.request(
        f"/conversations/{conversation_id}/messages",
        form={"content": first_message},
    )
    second.request(
        f"/conversations/{conversation_id}/messages",
        form={"content": second_message},
    )
    transcript = second.request(f"/conversations/{conversation_id}").text
    if first_message not in transcript or second_message not in transcript:
        raise RuntimeError("The online conversation did not persist both messages")
    report = first.request(
        f"/conversations/{conversation_id}/report",
        form={"reason": "发布核验举报记录"},
    )
    if "举报已记录" not in report.text:
        raise RuntimeError("The online report was not accepted")
    blocked = first.request(f"/conversations/{conversation_id}/block", form={})
    if "已拉黑对方" not in blocked.text:
        raise RuntimeError("The online block was not accepted")
    blocked_message = "This message must not persist after blocking"
    second.request(
        f"/conversations/{conversation_id}/messages",
        form={"content": blocked_message},
    )
    blocked_page = second.request(f"/conversations/{conversation_id}").text
    if blocked_message in blocked_page or "这段会话已停止联系" not in blocked_page:
        raise RuntimeError("The online block did not stop message persistence")


def verify_event_boundary(client: HttpClient) -> None:
    events = client.request("/events").text
    if "发起需手机号验证" not in events or 'href="/events/new"' in events:
        raise RuntimeError("The online event directory bypassed phone verification")
    rejected = client.request("/events/new", form={})
    if "发起线下饭局前需完成手机号验证" not in rejected.text:
        raise RuntimeError("The online event create request was not rejected")


def verify_persisted_transcript(client: HttpClient, conversation_id: str) -> None:
    result = client.request(f"/conversations/{conversation_id}")
    if "线上持久化核验：第一条消息" not in result.text:
        raise RuntimeError("The conversation did not survive the second deployment")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a disposable deployed real-user database without storing credentials."
    )
    parser.add_argument("base_url")
    parser.add_argument("edge_ip")
    parser.add_argument("--timeout", type=float, default=25.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SystemExit("base_url must be a credential-free HTTPS origin")
    edge_ip = str(ipaddress.ip_address(args.edge_ip))
    if not 1 <= args.timeout <= 30:
        raise SystemExit("--timeout must be between 1 and 30 seconds")

    run_id = secrets.token_hex(6)
    users = (
        QaUser(f"qa.realtags.{run_id}.one@example.test", secrets.token_urlsafe(32), "线上北辰一号"),
        QaUser(f"qa.realtags.{run_id}.two@example.test", secrets.token_urlsafe(32), "线上北辰二号"),
    )

    with pinned_dns(parsed.hostname, edge_ip):
        guest = HttpClient(args.base_url, args.timeout)
        if "进入预置演示账号" in guest.request("/").text:
            raise RuntimeError("The online environment exposed Demo login")
        guest.request("/demo/login", form={}, expected_status=404)

        first = HttpClient(args.base_url, args.timeout)
        second = HttpClient(args.base_url, args.timeout)
        register(first, users[0])
        register(second, users[1])
        source_states = sync_public_sources(first)
        conversation_id = start_conversation(first)
        verify_chat_and_safety(first, second, conversation_id)
        verify_event_boundary(first)
        print("PHASE1_READY " + " ".join(source_states), flush=True)
        input("Deploy the same commit again, then press Enter to continue: ")

        first_after_deploy = HttpClient(args.base_url, args.timeout)
        second_after_deploy = HttpClient(args.base_url, args.timeout)
        login(first_after_deploy, users[0])
        login(second_after_deploy, users[1])
        verify_persisted_transcript(second_after_deploy, conversation_id)
        print("PHASE2_PERSISTENCE_PASS", flush=True)
        print("DISPOSABLE_QA_DATABASE_READY_FOR_REMOVAL", flush=True)


if __name__ == "__main__":
    main()
