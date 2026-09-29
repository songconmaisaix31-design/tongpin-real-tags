from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from ..constants import (
    CITIES,
    DATA_SOURCE_ERROR_COPY,
    DATA_SOURCE_STATE_COPY,
    GENDERS,
    INTERESTS,
    MATCH_GENDERS,
    MBTIS,
    PURPOSES,
    SCHEDULES,
    ZODIACS,
)
from ..services.adapters import get_source_registry, source_connection_states, sync_source
from ..services.users import (
    ValidationError,
    authenticate,
    create_user,
    current_user,
    login_required,
    profile_tags,
    set_current_user,
)

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=("GET", "POST"))
def register():
    if current_user():
        return redirect(url_for("auth.profile"))
    if request.method == "POST":
        try:
            user_id = create_user(request.form)
        except ValidationError as error:
            flash(str(error), "error")
        else:
            set_current_user(user_id)
            success_message = "注册成功，已自动登录。下一步可同步无需凭据的公开行为数据。"
            if current_app.config["DEMO_MODE"]:
                success_message += "也可载入明确标注的演示数据。"
            flash(success_message, "success")
            return redirect(url_for("auth.connections"))
    return render_template(
        "register.html", cities=CITIES, genders=GENDERS, match_genders=MATCH_GENDERS,
        purposes=PURPOSES, interests=INTERESTS, mbtis=MBTIS, zodiacs=ZODIACS, schedules=SCHEDULES,
    )


@bp.route("/login", methods=("GET", "POST"))
def login():
    if current_user():
        return redirect(url_for("auth.profile"))
    if request.method == "POST":
        try:
            user = authenticate(request.form.get("email", ""), request.form.get("password", ""))
        except ValidationError as error:
            flash(str(error), "error")
        else:
            set_current_user(user["id"])
            return redirect(url_for("auth.profile"))
    return render_template("login.html")


@bp.post("/demo/login")
def demo_login():
    if not current_app.config["DEMO_MODE"]:
        abort(404)
    set_current_user("demo_001")
    flash("已进入预置演示账号。", "success")
    return redirect(url_for("auth.profile"))


@bp.post("/logout")
def logout():
    from flask import session

    session.clear()
    flash("已退出登录。", "success")
    return redirect(url_for("main.home"))


@bp.get("/profile")
@login_required
def profile():
    user = current_user()
    return render_template(
        "profile.html",
        user=user,
        tags=profile_tags(user["id"]),
        connections=source_connection_states(user["id"]),
    )


@bp.get("/profile/connections")
@login_required
def connections():
    user = current_user()
    registry = get_source_registry(
        timeout_seconds=float(current_app.config["DATA_SOURCE_TIMEOUT_SECONDS"])
    )
    return render_template(
        "connections.html",
        user=user,
        sources=tuple(registry.values()),
        connections=source_connection_states(user["id"]),
        state_copy=DATA_SOURCE_STATE_COPY,
    )


@bp.post("/profile/connections/<source>/sync")
@login_required
def sync_connection(source: str):
    user = current_user()
    registry = get_source_registry(
        timeout_seconds=float(current_app.config["DATA_SOURCE_TIMEOUT_SECONDS"])
    )
    definition = registry.get(source)
    if (
        definition is None
        or definition.data_mode == "unavailable"
        or (definition.data_mode == "fixture" and not current_app.config["DEMO_MODE"])
    ):
        abort(404)

    result = sync_source(
        user["id"],
        source,
        request.form.get("external_handle"),
        registry=registry,
    )
    if result.state == "ready" and result.data_mode == "public_live":
        flash(
            f"{definition.label} 已同步 {len(result.tags)} 个公开行为标签；公开账号归属尚未验证。",
            "success",
        )
    elif result.state == "ready":
        flash(f"{definition.label} 已载入 {len(result.tags)} 个 Fixture 演示标签。", "success")
    else:
        title, fallback_detail = DATA_SOURCE_STATE_COPY[result.state]
        detail = DATA_SOURCE_ERROR_COPY.get(result.error_code or "", fallback_detail)
        flash(f"{definition.label}：{title}。{detail}。", "error")
    return redirect(url_for("auth.connections"))
