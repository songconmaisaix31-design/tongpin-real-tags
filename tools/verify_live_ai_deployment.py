from __future__ import annotations

import argparse
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit


MAX_RESPONSE_BYTES = 1 * 1024 * 1024


@dataclass(frozen=True)
class ProbeResult:
    register_auto_login: bool
    empty_pool_ai_standby: bool
    ai_reply_stored: bool
    fixture_absent: bool
    secret_or_reply_content_emitted: bool = False


class SanitizedProbeFailure(RuntimeError):
    """Report a bounded step failure without command arguments or response bodies."""


def _vercel_executable() -> str:
    names = ("vercel.cmd", "vercel") if os.name == "nt" else ("vercel",)
    for name in names:
        executable = shutil.which(name)
        if executable:
            return executable
    raise SanitizedProbeFailure("Vercel CLI is not installed or not on PATH.")


def _curl_executable() -> str:
    names = ("curl.exe", "curl") if os.name == "nt" else ("curl",)
    for name in names:
        executable = shutil.which(name)
        if executable:
            return executable
    raise SanitizedProbeFailure("curl is not installed or not on PATH.")


def _read_bounded(path: Path) -> str:
    if not path.is_file():
        raise SanitizedProbeFailure("A probe response file was not created.")
    if path.stat().st_size > MAX_RESPONSE_BYTES:
        raise SanitizedProbeFailure("A probe response exceeded the bounded response size.")
    return path.read_text(encoding="utf-8", errors="replace")


class VercelCurlClient:
    def __init__(self, deployment: str, directory: Path, timeout_seconds: float) -> None:
        self.deployment = deployment
        self.directory = directory
        self.timeout_seconds = timeout_seconds
        self.vercel_executable = _vercel_executable()
        self.curl_executable = _curl_executable()
        self.cookie_path = directory / "session.cookies"

    def request(
        self,
        step: str,
        path: str,
        output_name: str,
        *,
        form: tuple[tuple[str, str], ...] | None = None,
        use_session: bool = False,
    ) -> str:
        output_path = self.directory / output_name
        curl_arguments = [
            "--silent",
            "--show-error",
            "--connect-timeout",
            "10",
            "--max-time",
            str(self.timeout_seconds),
            "--location",
            "--output",
            str(output_path),
        ]
        if use_session:
            command = [
                self.curl_executable,
                urljoin(self.deployment + "/", path.lstrip("/")),
                *curl_arguments,
                "--cookie",
                str(self.cookie_path),
            ]
        else:
            command = [
                self.vercel_executable,
                "curl",
                path,
                "--deployment",
                self.deployment,
                "--yes",
                "--",
                *curl_arguments,
                "--header",
                "x-vercel-set-bypass-cookie: true",
            ]
        command.extend(("--cookie-jar", str(self.cookie_path)))
        if form is not None:
            if not form:
                command.extend(("--data", ""))
            else:
                for key, value in form:
                    command.extend(("--data-urlencode", f"{key}={value}"))

        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds + (30 if use_session is False else 10),
            )
        except subprocess.TimeoutExpired as error:
            raise SanitizedProbeFailure(f"{step} exceeded its bounded timeout.") from error
        if completed.returncode != 0:
            raise SanitizedProbeFailure(f"{step} failed with exit code {completed.returncode}.")
        return _read_bounded(output_path)


def _validate_deployment(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise argparse.ArgumentTypeError("deployment must be a credential-free HTTPS origin")
    return value.rstrip("/")


def _registration_form(run_id: str) -> tuple[tuple[str, str], ...]:
    return (
        ("email", f"qa.ai.{run_id}@example.test"),
        ("password", "Qa9!" + secrets.token_urlsafe(32)),
        ("anonymous_alias", f"AI验证{run_id[:6]}"),
        ("city", "海外"),
        ("birth_year", "2000"),
        ("gender", "undisclosed"),
        ("match_gender", "male"),
        ("schedule", "正常"),
        ("mbti", "INTJ"),
        ("zodiac", "水瓶"),
        ("purposes", "随便聊聊"),
        ("interests", "人工智能"),
    )


def run_probe(deployment: str, timeout_seconds: float) -> ProbeResult:
    run_id = secrets.token_hex(6)
    test_message = f"请用一句简短中文确认本次 AI 候场验证，并明确你是 AI。验证编号 {run_id}。"
    with tempfile.TemporaryDirectory(prefix="realtags-live-ai-") as directory:
        client = VercelCurlClient(deployment, Path(directory), timeout_seconds)
        registration = client.request(
            "registration",
            "/register",
            "registration.html",
            form=_registration_form(run_id),
        )
        register_auto_login = (
            "注册成功，已自动登录" in registration and "数据连接" in registration
        )

        standby = client.request(
            "empty-pool matching",
            "/matches/search/start",
            "standby.html",
            form=(),
            use_session=True,
        )
        empty_pool_ai_standby = all(
            marker in standby
            for marker in (
                "AI 候场说明 · 非真人",
                'data-system-kind="ai_fallback_started"',
                "不会发送个人资料或标签",
            )
        )
        action = re.search(r'action="(?P<path>/conversations/[^\"]+/messages)"', standby)
        if action is None:
            raise SanitizedProbeFailure("The AI message action was not exposed.")

        reply = client.request(
            "controlled AI reply",
            html.unescape(action.group("path")),
            "reply.html",
            form=(("content", test_message),),
            use_session=True,
        )
        user_message_stored = test_message in reply
        mine_count = len(re.findall(r'class="chat-message mine', reply))
        theirs_count = len(re.findall(r'class="chat-message theirs', reply))
        ai_alias_visible = "AI 候场搭子" in reply
        provider_failure_visible = "AI 候场搭子暂时没能回复" in reply
        ai_reply_stored = all(
            (
                user_message_stored,
                mine_count >= 1,
                theirs_count >= 1,
                ai_alias_visible,
                not provider_failure_visible,
            )
        )
        if not ai_reply_stored:
            diagnostics = {
                "user_message_stored": user_message_stored,
                "mine_count": mine_count,
                "theirs_count": theirs_count,
                "ai_alias_visible": ai_alias_visible,
                "provider_failure_visible": provider_failure_visible,
            }
            raise SanitizedProbeFailure(
                "AI reply assertion failed: " + json.dumps(diagnostics, sort_keys=True)
            )

        events = client.request(
            "fixture contamination check",
            "/events",
            "events.html",
            use_session=True,
        )
        fixture_absent = "商家饭局 · Fixture" not in events and "event_00" not in events

    result = ProbeResult(
        register_auto_login=register_auto_login,
        empty_pool_ai_standby=empty_pool_ai_standby,
        ai_reply_stored=ai_reply_stored,
        fixture_absent=fixture_absent,
    )
    failed = [
        name
        for name, passed in (
            ("register_auto_login", result.register_auto_login),
            ("empty_pool_ai_standby", result.empty_pool_ai_standby),
            ("ai_reply_stored", result.ai_reply_stored),
            ("fixture_absent", result.fixture_absent),
            ("secret_or_reply_content_not_emitted", not result.secret_or_reply_content_emitted),
        )
        if not passed
    ]
    if failed:
        raise SanitizedProbeFailure("Failed assertions: " + ", ".join(failed) + ".")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify one live AI standby turn without emitting credentials or model content."
    )
    parser.add_argument("deployment", type=_validate_deployment)
    parser.add_argument("--timeout", type=float, default=35.0)
    args = parser.parse_args()
    if not 15 <= args.timeout <= 45:
        parser.error("--timeout must be between 15 and 45 seconds")
    return args


def main() -> None:
    args = parse_args()
    try:
        result = run_probe(args.deployment, args.timeout)
    except SanitizedProbeFailure as error:
        raise SystemExit(f"LIVE_AI_PROBE_FAIL: {error}") from None
    print(json.dumps(asdict(result), sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
