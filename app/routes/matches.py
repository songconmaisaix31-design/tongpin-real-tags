from __future__ import annotations

import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from ..services.ai_fallback import ai_fallback_available
from ..services.chat import start_ai_fallback_conversation, start_direct_conversation
from ..services.matching import ranked_matches
from ..services.users import ValidationError, current_user, get_user, login_required

bp = Blueprint("matches", __name__)
MATCH_FLOW_SESSION_KEY = "match_flow"
MATCH_FLOW_PHASES = {"searching", "result"}


def _flow_for(user_id: str) -> dict:
    raw = session.get(MATCH_FLOW_SESSION_KEY)
    if not isinstance(raw, dict) or raw.get("user_id") != user_id:
        return {"user_id": user_id, "phase": None, "attempt_id": None, "candidate_id": None, "seen_ids": []}
    seen_ids = raw.get("seen_ids")
    if not isinstance(seen_ids, list):
        seen_ids = []
    return {
        "user_id": user_id,
        "phase": raw.get("phase") if raw.get("phase") in MATCH_FLOW_PHASES else None,
        "attempt_id": raw.get("attempt_id") if isinstance(raw.get("attempt_id"), str) else None,
        "candidate_id": raw.get("candidate_id") if isinstance(raw.get("candidate_id"), str) else None,
        "seen_ids": list(dict.fromkeys(item for item in seen_ids[:20] if isinstance(item, str))),
    }


def _matches_attempt(flow: dict, phase: str) -> bool:
    supplied = request.form.get("attempt_id", "")
    expected = flow.get("attempt_id") or ""
    return flow.get("phase") == phase and bool(supplied) and secrets.compare_digest(supplied, expected)


def _find_match(viewer_id: str, candidate_id: str | None) -> dict | None:
    if not candidate_id:
        return None
    return next((item for item in ranked_matches(viewer_id) if item["candidate"]["id"] == candidate_id), None)


def _is_result_reference(flow: dict, supplied: str) -> bool:
    return any(
        isinstance(expected, str) and secrets.compare_digest(supplied, expected)
        for expected in (flow.get("candidate_id"), flow.get("attempt_id"))
    )


def _result_projection(match: dict, attempt_id: str) -> dict:
    """Return only fields permitted in the L0 template context."""
    return {
        "display_score": match["display_score"],
        "common_point_count": match["common_point_count"],
        # The existing template needs an action reference, never the profile id.
        "candidate": {"id": attempt_id},
    }


def _start_attempt(user_id: str, match: dict, seen_ids: list[str]) -> dict:
    candidate_id = match["candidate"]["id"]
    flow = {
        "user_id": user_id,
        "phase": "searching",
        "attempt_id": secrets.token_urlsafe(12),
        "candidate_id": candidate_id,
        "seen_ids": list(dict.fromkeys([*seen_ids, candidate_id])),
    }
    session[MATCH_FLOW_SESSION_KEY] = flow
    return flow


def _redirect_to_ai_fallback(user_id: str):
    if not ai_fallback_available():
        return None
    try:
        conversation_id = start_ai_fallback_conversation(user_id)
    except ValidationError as error:
        flash(str(error), "error")
        return None
    session.pop(MATCH_FLOW_SESSION_KEY, None)
    flash("当前没有符合条件的真人候选，已进入明确标注的 AI 候场互动。", "info")
    return redirect(url_for("chat.detail", conversation_id=conversation_id))


@bp.get("/matches")
@login_required
def index():
    user = current_user()
    matches = ranked_matches(user["id"])
    return render_template(
        "matches.html",
        candidate_count=len(matches),
        ai_fallback_available=ai_fallback_available(),
    )


@bp.post("/matches/search/start")
@login_required
def search_start():
    user = current_user()
    matches = ranked_matches(user["id"])
    if not matches:
        fallback = _redirect_to_ai_fallback(user["id"])
        if fallback is not None:
            return fallback
        flash("暂时没有符合硬性筛选条件的候选人。我们不会为了填满结果而放宽你的偏好。", "info")
        return redirect(url_for("matches.index"))

    flow = _flow_for(user["id"])
    if flow["phase"] == "searching" and _find_match(user["id"], flow["candidate_id"]):
        return redirect(url_for("matches.searching"))

    _start_attempt(user["id"], matches[0], [])
    return redirect(url_for("matches.searching"))


@bp.get("/matches/searching")
@login_required
def searching():
    user = current_user()
    flow = _flow_for(user["id"])
    if flow["phase"] != "searching" or _find_match(user["id"], flow["candidate_id"]) is None:
        session.pop(MATCH_FLOW_SESSION_KEY, None)
        flash("当前没有进行中的匹配，请重新开始。", "info")
        return redirect(url_for("matches.index"))
    return render_template("match_searching.html", attempt_id=flow["attempt_id"])


@bp.post("/matches/search/complete")
@login_required
def search_complete():
    user = current_user()
    flow = _flow_for(user["id"])
    if not _matches_attempt(flow, "searching"):
        flash("这次匹配已失效，请重新开始。", "info")
        return redirect(url_for("matches.index"))
    match = _find_match(user["id"], flow["candidate_id"])
    if match is None:
        matches = ranked_matches(user["id"])
        seen_ids = set(flow["seen_ids"])
        replacement = next(
            (item for item in matches if item["candidate"]["id"] not in seen_ids),
            matches[0] if matches else None,
        )
        if replacement is not None:
            _start_attempt(user["id"], replacement, flow["seen_ids"])
            flash("候选状态刚刚变化，已自动继续寻找下一位真人。", "info")
            return redirect(url_for("matches.searching"))
        fallback = _redirect_to_ai_fallback(user["id"])
        if fallback is not None:
            return fallback
        session.pop(MATCH_FLOW_SESSION_KEY, None)
        flash("候选状态刚刚变化，请稍后重新匹配。", "info")
        return redirect(url_for("matches.index"))
    flow["phase"] = "result"
    session[MATCH_FLOW_SESSION_KEY] = flow
    return redirect(url_for("matches.detail", candidate_id=flow["candidate_id"]))


@bp.post("/matches/search/cancel")
@login_required
def search_cancel():
    user = current_user()
    flow = _flow_for(user["id"])
    if not _matches_attempt(flow, "searching"):
        flash("匹配状态已经更新，没有取消任何新任务。", "info")
        return redirect(url_for("matches.index"))
    session.pop(MATCH_FLOW_SESSION_KEY, None)
    flash("已取消本次匹配，没有建立任何会话。", "success")
    return redirect(url_for("matches.index"))


@bp.post("/matches/search/retry")
@login_required
def search_retry():
    user = current_user()
    flow = _flow_for(user["id"])
    if not _matches_attempt(flow, "result"):
        flash("当前结果已经更新，请重新开始匹配。", "info")
        return redirect(url_for("matches.index"))

    matches = ranked_matches(user["id"])
    current_id = flow["candidate_id"]
    seen_ids = flow["seen_ids"]
    selected = next((item for item in matches if item["candidate"]["id"] not in set(seen_ids)), None)
    if selected is None:
        selected = next((item for item in matches if item["candidate"]["id"] != current_id), None)
        seen_ids = [current_id] if selected else []
    if selected is None:
        flash("候选池里暂时没有其他人，稍后再来试试。", "info")
        return redirect(url_for("matches.detail", candidate_id=current_id))

    _start_attempt(user["id"], selected, seen_ids)
    return redirect(url_for("matches.searching"))


@bp.get("/matches/<candidate_id>")
@login_required
def detail(candidate_id: str):
    user = current_user()
    flow = _flow_for(user["id"])
    if flow["phase"] != "result" or flow["candidate_id"] != candidate_id:
        abort(404)
    match = _find_match(user["id"], flow["candidate_id"])
    if match is None:
        abort(404)
    return render_template(
        "match_detail.html",
        match=_result_projection(match, flow["attempt_id"]),
        attempt_id=flow["attempt_id"],
    )


@bp.post("/matches/<candidate_id>/start")
@login_required
def start(candidate_id: str):
    user = current_user()
    flow = _flow_for(user["id"])
    if not _is_result_reference(flow, candidate_id) or not _matches_attempt(flow, "result"):
        flash("这次匹配结果已失效，请重新开始。", "info")
        return redirect(url_for("matches.index"))
    try:
        conversation_id = start_direct_conversation(user["id"], flow["candidate_id"])
    except ValidationError as error:
        flash(str(error), "error")
        return redirect(url_for("matches.index"))
    session.pop(MATCH_FLOW_SESSION_KEY, None)
    return redirect(url_for("chat.detail", conversation_id=conversation_id))
